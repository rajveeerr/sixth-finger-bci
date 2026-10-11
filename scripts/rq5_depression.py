"""RQ5: segment-level vs subject-level cross-validation in public depression EEG (P09 Study 6).

Everything is fixed in _workspace/research/preregistration-rq5.md (tag prereg-rq5-v1):

uv run python scripts/rq5_depression.py fetch       # downloads; refuses before the tag
uv run python scripts/rq5_depression.py audit       # results/audit/rq5_audit_<dataset>.csv
uv run python scripts/rq5_depression.py run         # both pipelines, both protocols, E1-E3
uv run python scripts/rq5_depression.py summarise   # results/summary/rq5_*.csv and the figure

Privacy: the primary dataset's EDF headers hold names in the patient field. Only the channel
labels, the sampling rate and the start date are read from a header; linked recordings are
found by comparing SHA-256 hashes of the patient field. Header text is never printed, logged,
stored or committed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import welch
from sklearn.base import BaseEstimator, TransformerMixin

from sixthfinger.paths import get_paths

log = logging.getLogger("rq5")
TAG = "prereg-rq5-v1"
CHANNELS = ["Fp1", "Fp2", "F7", "F3", "Fz", "F4", "F8", "T3", "C3", "Cz", "C4", "T4", "T5",
            "P3", "Pz", "P4", "T6", "O1", "O2"]  # fmt: skip
# Preregistration-rq5 §2.2: the HydroCel GSN-129 electrode for each name above.
MODMA_CHANNELS = {"Fp1": "E22", "Fp2": "E9", "F7": "E26", "F3": "E24", "Fz": "E11",
                  "F4": "E124", "F8": "E2", "T3": "E39", "C3": "E36", "Cz": "Cz",
                  "C4": "E104", "T4": "E115", "T5": "E50", "P3": "E52", "Pz": "E62",
                  "P4": "E92", "T6": "E101", "O1": "E70", "O2": "E83"}  # fmt: skip
SFREQ, SEG_S, SKIP_S, KEEP_S = 128, 4.0, 5.0, 300.0
P2P_MAX, P2P_MIN, MIN_SEGMENTS = 200.0, 0.5, 20  # µV, µV, segments
MUMTAZ_API = "https://api.figshare.com/v2/articles/4244171/versions/2"
MODMA_URL = (
    "https://reshare.ukdataservice.ac.uk/854301/4/854301_EEG_128Channels_Resting_Lanzhou_2015.zip"
)
MODMA_MD5 = "32b0dd6eb897c1617c19cfd529f7aad5"
MODMA_RECORD = "https://reshare.ukdataservice.ac.uk/854301/"


def data_dir() -> Path:
    return get_paths().data / "depression"


def require_tag() -> None:
    """Nothing is downloaded before the pre-registration (its gate in P09 step 4.5)."""
    root = get_paths().root
    ok = subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", TAG, "HEAD"], capture_output=True
    ).returncode == 0  # fmt: skip
    if not ok:
        raise SystemExit(f"{TAG} is not an ancestor of HEAD: freeze RQ5 first")


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download(url: str, dest: Path) -> int:
    """Download to dest (atomically); the HTTP status, 200 on success."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=120) as r, tmp.open("wb") as f:
            while block := r.read(1 << 20):
                f.write(block)
    except urllib.error.HTTPError as err:
        tmp.unlink(missing_ok=True)
        return err.code
    tmp.replace(dest)
    return 200


# EDF headers (primary dataset) ---------------------------------------------------------------


def edf_patient_hash(path: Path) -> str:
    """SHA-256 of the 80-byte local patient field (EDF bytes 8-88); the field is not kept."""
    with path.open("rb") as f:
        head = f.read(256)
    return hashlib.sha256(head[8:88]).hexdigest()


def edf_start_year(path: Path) -> int:
    """Recording year from the start date (EDF bytes 168-176, dd.mm.yy; 1985-2084 rule)."""
    with path.open("rb") as f:
        yy = int(f.read(256)[174:176].decode("ascii"))
    return 1900 + yy if yy >= 85 else 2000 + yy


def channel_name(label: str) -> str:
    """'EEG Fp1-LE' -> 'Fp1': drop a leading 'EEG ' and everything from the first '-'."""
    label = label.strip()
    if label.upper().startswith("EEG "):
        label = label[4:]
    return label.split("-")[0].strip()


def match_channels(labels: list[str], wanted: list[str]) -> dict[str, str] | None:
    """The file label for each wanted name (case-insensitive), or None if one is missing."""
    by_name = {channel_name(lab).lower(): lab for lab in labels}
    if not all(w.lower() in by_name for w in wanted):
        return None
    return {w: by_name[w.lower()] for w in wanted}


def mumtaz_files(meta: dict) -> pd.DataFrame:
    """The eyes-closed files of the figshare record, with group-prefixed subject ids."""
    rows = []
    for f in meta["files"]:
        name = f["name"]
        parts = name.replace(".edf", "").split()
        if len(parts) == 3 and parts[2] == "EC" and parts[0] in ("H", "MDD"):
            rows.append(dict(file=name, subject=f"{parts[0]}-{parts[1]}", group=parts[0],
                             url=f["download_url"], md5=f["computed_md5"],
                             number=int(parts[1][1:])))  # fmt: skip
    return pd.DataFrame(rows).sort_values(["group", "number"]).reset_index(drop=True)


# Segments ------------------------------------------------------------------------------------


def segment(data_uv: np.ndarray, sfreq: float, step_s: float = SEG_S) -> np.ndarray:
    """Preregistration-rq5 §3 steps 4-6 on a (19, n) µV recording at 128 Hz.

    Drop the first 5 s, keep up to 300 s, cut 4 s segments every step_s seconds, and drop a
    segment in which any channel's peak-to-peak amplitude is above 200 µV or below 0.5 µV.
    """
    start, stop = int(SKIP_S * sfreq), int((SKIP_S + KEEP_S) * sfreq)
    x = data_uv[:, start:stop]
    n, step = int(SEG_S * sfreq), int(step_s * sfreq)
    starts = range(0, x.shape[1] - n + 1, step)
    segs = np.stack([x[:, s : s + n] for s in starts]) if len(starts) else np.empty((0, *x.shape))
    p2p = segs.max(axis=-1) - segs.min(axis=-1)
    keep = (p2p <= P2P_MAX).all(axis=1) & (p2p >= P2P_MIN).all(axis=1)
    return segs[keep].astype(np.float32)


def preprocess(raw, picks: dict[str, str]):
    """§3 steps 1-3: the 19 channels, 1-40 Hz, 128 Hz, average reference; data in µV."""
    raw = raw.copy().pick(list(picks.values()))
    raw.rename_channels({v: k for k, v in picks.items()})
    raw.reorder_channels(CHANNELS)
    raw.filter(1.0, 40.0, verbose="ERROR")
    raw.resample(SFREQ, verbose="ERROR")
    raw.set_eeg_reference("average", verbose="ERROR")
    return raw.get_data() * 1e6


# Pipelines and protocols (preregistration-rq5 §4-5) ------------------------------------------

BANDS = [(1, 4), (4, 8), (8, 13), (13, 30), (30, 40)]
PIPELINES = ("bp_lr", "ts_lr")
PROTOCOLS = ("segment_cv", "subject_cv")


class LogBandPower(BaseEstimator, TransformerMixin):
    """Welch log band power per channel (2 s Hann windows, 50 % overlap): 19 x 5 features."""

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        f, psd = welch(X, fs=SFREQ, window="hann", nperseg=2 * SFREQ, noverlap=SFREQ, axis=-1)
        bands = [psd[..., (f >= lo) & (f < hi)].mean(axis=-1) for lo, hi in BANDS]
        return np.log(np.stack(bands, axis=-1)).reshape(len(X), -1)


def pipeline(name: str):
    from pyriemann.estimation import Covariances
    from pyriemann.tangentspace import TangentSpace
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    lr = LogisticRegression(C=1.0, max_iter=1000)
    if name == "bp_lr":
        return make_pipeline(LogBandPower(), StandardScaler(), lr)
    return make_pipeline(Covariances("oas"), TangentSpace(metric="riemann"), lr)


def splits(md: pd.DataFrame, protocol: str):
    """Ten folds; every segment is tested once. subject_cv keeps each split group whole."""
    from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold

    y = (md.group == "MDD").to_numpy().astype(int)
    if protocol == "segment_cv":
        return list(StratifiedKFold(10, shuffle=True, random_state=0).split(md, y))
    cv = StratifiedGroupKFold(10, shuffle=True, random_state=0)
    return list(cv.split(md, y, groups=md.split_group.to_numpy()))


def evaluate(X: np.ndarray, md: pd.DataFrame, pipe_name: str, protocol: str) -> pd.DataFrame:
    """Out-of-fold P(MDD) for every segment; the whole pipeline is fitted inside each fold."""
    from sklearn.base import clone

    y = (md.group == "MDD").to_numpy().astype(int)
    proba = np.full(len(md), np.nan)
    template = pipeline(pipe_name)
    for train, test in splits(md, protocol):
        if protocol == "subject_cv" and set(md.split_group.iloc[train]) & set(
            md.split_group.iloc[test]
        ):
            raise AssertionError("a split group on both sides of a subject-level split")
        model = clone(template).fit(X[train], y[train])
        proba[test] = model.predict_proba(X[test])[:, 1]
    if np.isnan(proba).any():
        raise AssertionError("a segment was never tested")
    return md.assign(p_mdd=proba, correct=(proba > 0.5) == (y == 1))


def per_subject(pred: pd.DataFrame) -> pd.DataFrame:
    """a = share of a subject's segments assigned to its own group (preregistration-rq5 §1)."""
    return pred.groupby(["subject", "group", "split_group"], as_index=False).agg(
        a=("correct", "mean"), n_segments=("correct", "size")
    )


def subject_balanced_accuracy(values: pd.DataFrame) -> float:
    return float(values.groupby("group").a.mean().mean())


def fetch(_args) -> None:
    require_tag()
    out = data_dir() / "mumtaz"
    out.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(MUMTAZ_API, timeout=60) as r:
        meta = json.load(r)
    (out / "figshare_record.json").write_text(json.dumps(meta, indent=1))
    files = mumtaz_files(meta)
    status = []
    for f in files.itertuples():
        dest = out / f.file
        code = 200 if dest.exists() and md5(dest) == f.md5 else download(f.url, dest)
        ok = code == 200 and md5(dest) == f.md5
        status.append(dict(file=f.file, http=code, md5_ok=ok))
        log.info("%s: %s", f.file, "ok" if ok else f"failed ({code})")
    pd.DataFrame(status).to_csv(out / "download_status.csv", index=False)
    modma = data_dir() / "modma"
    modma.mkdir(parents=True, exist_ok=True)
    zip_path = modma / MODMA_URL.rsplit("/", 1)[1]
    download(MODMA_RECORD, modma / "reshare_record.html")  # the access terms on the day
    if not (zip_path.exists() and md5(zip_path) == MODMA_MD5):
        code = download(MODMA_URL, zip_path)
        log.info("MODMA zip: %s", code)
    log.info("MODMA zip md5 ok: %s", md5(zip_path) == MODMA_MD5)


def audit_mumtaz() -> tuple[pd.DataFrame, list]:
    """One row per eyes-closed file; and the kept recordings' segments with their subject."""
    import mne

    out = data_dir() / "mumtaz"
    files = mumtaz_files(json.loads((out / "figshare_record.json").read_text()))
    status = pd.read_csv(out / "download_status.csv").set_index("file")
    rows, kept, seen_md5 = [], [], {}
    hashes = {}
    for f in files.itertuples():
        row = dict(dataset="mumtaz", file=f.file, subject=f.subject, group=f.group, kept=False)
        path = out / f.file
        if not status.loc[f.file, "md5_ok"]:
            rows.append({**row, "reason": f"not downloadable (HTTP {status.loc[f.file, 'http']})"})
            continue
        if f.md5 in seen_md5:
            rows.append({**row, "reason": f"byte-identical to {seen_md5[f.md5]}"})
            continue
        seen_md5[f.md5] = f.subject
        raw = mne.io.read_raw_edf(path, preload=True, verbose="ERROR")
        picks = match_channels(raw.ch_names, CHANNELS)
        if picks is None:
            rows.append({**row, "reason": "a required channel is missing"})
            continue
        segs = segment(preprocess(raw, picks), SFREQ)
        duration = raw.n_times / raw.info["sfreq"]
        del raw  # its info holds the header's patient fields; nothing of it is kept
        hashes[f.subject] = edf_patient_hash(path)
        row.update(year=edf_start_year(path), duration_s=round(duration, 1), n_segments=len(segs))
        if len(segs) < MIN_SEGMENTS:
            rows.append({**row, "reason": f"fewer than {MIN_SEGMENTS} accepted segments"})
            continue
        rows.append({**row, "kept": True, "reason": ""})
        kept.append((f.subject, f.group, segs, path))
    audit = pd.DataFrame(rows)
    # Linked recordings: the same patient field (compared by hash) is one split group.
    by_hash: dict[str, list[str]] = {}
    for subject, h in hashes.items():
        by_hash.setdefault(h, []).append(subject)
    group_of = {s: "+".join(sorted(m)) for m in by_hash.values() for s in m}
    audit["split_group"] = audit.subject.map(group_of).fillna(audit.subject)
    return audit, kept


def save_segments(name: str, audit: pd.DataFrame, kept: list) -> None:
    out = data_dir() / "derived"
    out.mkdir(parents=True, exist_ok=True)
    split = audit.set_index("subject").split_group
    X = np.concatenate([segs for _, _, segs, _ in kept])
    md = pd.concat(
        [pd.DataFrame({"subject": s, "group": g, "split_group": split[s], "segment": range(len(x))})
         for s, g, x, _ in kept],
        ignore_index=True,
    )  # fmt: skip
    np.save(out / f"{name}_X.npy", X)
    md.to_parquet(out / f"{name}_segments.parquet", index=False)


def audit(_args) -> None:
    require_tag()
    paths = get_paths()
    table, kept = audit_mumtaz()
    table.to_csv(paths.audit / "rq5_audit_mumtaz.csv", index=False)
    save_segments("mumtaz", table, kept)
    log.info("mumtaz: %d files, %d kept (%s)", len(table), table.kept.sum(),
             table[table.kept].group.value_counts().to_dict())  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("fetch", fetch), ("audit", audit)):
        sub.add_parser(name).set_defaults(fn=fn)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    args.fn(args)


if __name__ == "__main__":
    main()
