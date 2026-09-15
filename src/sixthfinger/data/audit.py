"""Integrity audit of the downloaded runs."""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import correlate

from sixthfinger.data.channels import CHANNELS_40
from sixthfinger.data.loading import RunInfo, list_processed_runs, read_eeglab_mat

log = logging.getLogger(__name__)

EXPECTED_EVENTS = {"1": 20, "2": 10, "3": 10}
EXPECTED_CHANNELS = 43
# A run with fewer imagery cues than this, or shorter than this, is not a usable run.
MIN_MI_EVENTS = 10
MIN_DURATION_S = 120.0

# Recordings known to be duplicated (05-DATASET-DOSSIER.md §6); always compared run by run.
KNOWN_DUPLICATES = [
    (("sub-02", "post"), ("sub-02", "follow")),
    (("sub-21", "pre"), ("sub-22", "pre")),
]

SEGMENT_S = 20.0  # length of each piece of run b that is searched for in run a
SEARCH_S = 60.0  # how far (each way) the piece may have moved
SCREEN_SEGMENTS = 3

SAME_RECORDING_R = 0.90
SHARED_RECORDING_R = 0.30


def audit_run(path: Path) -> dict:
    rec = read_eeglab_mat(path)
    codes = pd.Series(rec.event_codes, dtype=str)
    idx = [rec.ch_names.index(c) for c in CHANNELS_40]
    x = rec.data_uv[idx]
    cue_gaps = _cue_gaps_s(rec.event_codes, rec.event_samples, rec.sfreq)
    return {
        "file": path.name,
        "n_channels": len(rec.ch_names),
        "sfreq": rec.sfreq,
        "duration_s": round(rec.data_uv.shape[1] / rec.sfreq, 2),
        "n_rest": int((codes == "1").sum()),
        "n_ah": int((codes == "2").sum()),
        "n_sf": int((codes == "3").sum()),
        "n_boundary": int((codes == "boundary").sum()),
        "abs_median_uv": float(np.median(np.abs(x))),
        "abs_p99_uv": float(np.percentile(np.abs(x), 99)),
        "flat_channels": int((x.std(axis=1) < 1e-3).sum()),
        "cue_gap_median_s": float(np.median(cue_gaps)) if cue_gaps.size else np.nan,
        "cue_gap_min_s": float(cue_gaps.min()) if cue_gaps.size else np.nan,
    }


def _cue_gaps_s(codes: list[str], samples: np.ndarray, sfreq: float) -> np.ndarray:
    # Time from each rest onset to the imagery cue that follows it.
    gaps = [
        (samples[i + 1] - samples[i]) / sfreq
        for i, code in enumerate(codes[:-1])
        if code == "1" and codes[i + 1] in ("2", "3")
    ]
    return np.asarray(gaps, dtype=float)


def audit_all(processed_dir: Path) -> pd.DataFrame:
    rows = []
    for info in list_processed_runs(processed_dir):
        row = audit_run(info.path)
        row.update(subject=info.subject, group=info.group, session=info.session, run=info.run)
        rows.append(row)
    cols = ["subject", "group", "session", "run"]
    df = pd.DataFrame(rows)
    return df[cols + [c for c in df.columns if c not in cols]]


def event_flags(inventory: pd.DataFrame) -> pd.DataFrame:
    """Runs that differ from the nominal design, with the kind of difference.

    `count` (event counts differ from 20/10/10) is common and expected: EEGLAB removed
    events together with cut segments. `degenerate` runs hold too little imagery to use.
    """
    inv = inventory
    count = (
        (inv.n_rest != EXPECTED_EVENTS["1"])
        | (inv.n_ah != EXPECTED_EVENTS["2"])
        | (inv.n_sf != EXPECTED_EVENTS["3"])
    )
    format_ = (inv.n_channels != EXPECTED_CHANNELS) | (inv.sfreq != 250.0) | (inv.flat_channels > 0)
    degenerate = ((inv.n_ah + inv.n_sf) < MIN_MI_EVENTS) | (inv.duration_s < MIN_DURATION_S)
    flag = np.select([degenerate, format_, count], ["degenerate", "format", "count"], "")
    out = inv.assign(flag=flag)
    return out[out.flag != ""]


def c3_trace(path: Path) -> np.ndarray:
    """C3 at the full 250 Hz, z-scored.

    No decimation: the data hold 5-35 Hz, and a lag error of a few samples already
    destroys the correlation at 25-35 Hz.
    """
    rec = read_eeglab_mat(path)
    x = rec.data_uv[rec.ch_names.index("C3")].astype(np.float64)
    return ((x - x.mean()) / x.std()).astype(np.float32)


def segment_max_r(a: np.ndarray, b: np.ndarray, start: int, seg: int, search: int) -> float:
    """Max |Pearson r| of b[start:start+seg] against every same-length piece of a
    whose start lies within +/- search samples of `start`."""
    s = b[start : start + seg].astype(np.float64)
    s = s - s.mean()
    lo, hi = max(0, start - search), min(a.size, start + seg + search)
    ref = a[lo:hi].astype(np.float64)
    if ref.size < seg or s.std() == 0:
        return float("nan")
    c = correlate(ref, s, mode="valid", method="fft")
    cs = np.concatenate([[0.0], np.cumsum(ref)])
    cs2 = np.concatenate([[0.0], np.cumsum(ref**2)])
    mean = (cs[seg:] - cs[:-seg]) / seg
    var = np.maximum((cs2[seg:] - cs2[:-seg]) / seg - mean**2, 1e-12)
    return float(np.max(np.abs(c / (seg * np.sqrt(var) * s.std()))))


def segment_similarity(
    a: np.ndarray, b: np.ndarray, sfreq: float = 250.0, n_segments: int | None = None
) -> float:
    """Median over 20 s pieces of b of their best |r| in a (+/- 60 s).

    Works although EEGLAB cut different stretches out of two copies of one recording:
    each piece is aligned on its own. n_segments=None uses every piece (confirmation);
    a small number spreads that many pieces over the run (cheap screening).
    """
    seg, search = int(SEGMENT_S * sfreq), int(SEARCH_S * sfreq)
    starts = np.arange(0, b.size - seg + 1, seg)
    if n_segments is not None and starts.size > n_segments:
        pick = np.linspace(0, starts.size - 1, n_segments + 2)[1:-1].round().astype(int)
        starts = starts[pick]
    rs = [segment_max_r(a, b, int(st), seg, search) for st in starts]
    return float(np.nanmedian(rs)) if rs else float("nan")


def known_pairs(runs: list[RunInfo]) -> list[tuple[str, str]]:
    """File-name pairs of the known duplicates, matched run by run."""
    by_key = {(r.subject, r.session, r.run): r.path.name for r in runs}
    pairs = []
    for (sa, ses_a), (sb, ses_b) in KNOWN_DUPLICATES:
        for run in ("01", "02", "03", "04"):
            a, b = by_key.get((sa, ses_a, run)), by_key.get((sb, ses_b, run))
            if a and b:
                pairs.append((a, b))
    return pairs


def pairwise_similarity(
    processed_dir: Path,
    screen_threshold: float = 0.25,
    forced_pairs: list[tuple[str, str]] | None = None,
) -> pd.DataFrame:
    """Screen every pair of runs cheaply, then confirm candidates on every segment."""
    runs = list_processed_runs(processed_dir)
    names = [r.path.name for r in runs]
    traces = [c3_trace(r.path) for r in runs]  # about 85 MB for 268 runs at float32
    forced = {tuple(sorted(p)) for p in (forced_pairs or [])}
    rows = []
    for i in range(len(runs)):
        for j in range(i + 1, len(runs)):
            is_forced = tuple(sorted((names[i], names[j]))) in forced
            screen = segment_similarity(traces[i], traces[j], n_segments=SCREEN_SEGMENTS)
            if screen >= screen_threshold or is_forced:
                rows.append(
                    {"run_a": names[i], "run_b": names[j], "screen_r": screen, "forced": is_forced}
                )
        log.info("screened %s (%d/%d)", names[i], i + 1, len(runs))
    for row in rows:
        a, b = traces[names.index(row["run_a"])], traces[names.index(row["run_b"])]
        row["segment_median_r"] = segment_similarity(a, b)
    cols = ["run_a", "run_b", "screen_r", "segment_median_r", "forced"]
    df = pd.DataFrame(rows, columns=cols)
    return df.sort_values("segment_median_r", ascending=False, ignore_index=True)


def verdict(r: float) -> str:
    if r >= SAME_RECORDING_R:
        return "same recording"
    if r >= SHARED_RECORDING_R:
        return "shared recording, differently processed"
    return "independent"


def raw_crc_duplicates(url: str) -> pd.DataFrame:
    """Byte-identical files in a remote zip, from its central directory only (a few kB)."""
    from remotezip import RemoteZip

    groups: dict[tuple[int, int], list[str]] = defaultdict(list)
    with RemoteZip(url) as z:
        for info in z.infolist():
            if not info.is_dir():
                groups[(info.CRC, info.file_size)].append(info.filename)
    rows = [
        {"crc32": f"{crc:08x}", "size": size, "files": ";".join(sorted(files))}
        for (crc, size), files in groups.items()
        if len(files) > 1
    ]
    return pd.DataFrame(rows, columns=["crc32", "size", "files"])


def write_report(audit_dir: Path) -> Path:
    """Markdown summary of the CSVs in audit_dir; decisions are added by hand below it."""
    inv = pd.read_csv(audit_dir / "inventory.csv", dtype={"run": str})
    flags = pd.read_csv(audit_dir / "event_flags.csv", dtype={"run": str})
    dup = pd.read_csv(audit_dir / "near_duplicates.csv")
    dup = dup.assign(verdict=dup.segment_median_r.map(verdict))
    shown = dup[(dup.verdict != "independent") | dup.forced]
    unusual = flags[flags.flag != "count"]
    lines = [
        "# Data integrity audit",
        "",
        f"Runs: {len(inv)}; sessions: {inv.groupby(['subject', 'session']).ngroups}.",
        "",
        "## Runs per session",
        "",
        inv.groupby("session").size().rename("runs").to_frame().to_markdown(),
        "",
        "## Flagged runs",
        "",
        flags.flag.value_counts().rename("runs").to_frame().to_markdown() if len(flags) else "none",
        "",
        unusual[
            ["subject", "session", "run", "duration_s", "n_rest", "n_ah", "n_sf", "flag"]
        ].to_markdown(index=False)
        if len(unusual)
        else "No run is degenerate or has an unexpected format.",
        "",
        "## Pairs of runs that share a recording",
        "",
        f"Screened {len(inv) * (len(inv) - 1) // 2} pairs; {len(dup)} confirmed on every segment.",
        "",
        shown.to_markdown(index=False, floatfmt=".3f") if len(shown) else "none",
        "",
    ]
    crc = audit_dir / "raw_crc_duplicates.csv"
    if crc.exists():
        lines += [
            "## Byte-identical raw files (sourcedata.zip index)",
            "",
            pd.read_csv(crc).to_markdown(index=False),
            "",
        ]
    lines += ["## Decisions", "", "(filled in by hand in step 4.6)", ""]
    out = audit_dir / "audit_report.md"
    out.write_text("\n".join(lines))
    return out
