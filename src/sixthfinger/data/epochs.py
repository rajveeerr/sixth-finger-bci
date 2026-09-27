"""Cut fixed windows around cues and cache them per session."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from sixthfinger import __version__
from sixthfinger.config import DataConfig
from sixthfinger.data.channels import hemiplegia_side, mirror_if_needed, subject_group
from sixthfinger.data.loading import list_processed_runs, read_eeglab_mat

log = logging.getLogger(__name__)

MI_CODES = ("2", "3")
DROP_COLS = ["file", "code", "trial_in_run", "reason", "subject", "session"]


@dataclass
class SessionWindows:
    X: np.ndarray  # (n, 40, n_times) float32, volts
    y: np.ndarray  # (n,) int64
    trial_uid: np.ndarray  # (n,) str
    run: np.ndarray  # (n,) int8
    trial_in_run: np.ndarray  # (n,) int16
    onset_s: np.ndarray  # (n,) float64, window start within its run file
    dropped: list[dict]  # one dict per window that could not be cut


def assign_trials(codes: list[str]) -> list[int]:
    """Trial number (1-based) for every event; 0 for events that are not REST/AH/SF.

    A REST marker ('1') opens a trial. An imagery cue belongs to the trial opened by
    the '1' immediately before it, if no other cue came in between. A cue without
    its own '1' (the marker was cut out with a data segment) gets a trial of its own,
    so one trial never holds two imagery windows.
    """
    out, trial, open_rest = [], 0, False
    for code in codes:
        if code == "1":
            trial += 1
            open_rest = True
            out.append(trial)
        elif code in MI_CODES:
            if not open_rest:
                trial += 1
            open_rest = False
            out.append(trial)
        else:
            out.append(0)
    return out


def cut_run(path: Path, cfg: DataConfig) -> tuple[list, list[dict]]:
    rec = read_eeglab_mat(path)
    if rec.sfreq != cfg.signal.sfreq:
        raise ValueError(f"{path.name}: sfreq {rec.sfreq} != config {cfg.signal.sfreq}")
    idx = [rec.ch_names.index(c) for c in cfg.channels.keep]
    data = rec.data_uv[idx].astype(np.float32) * np.float32(cfg.signal.scale_to_volts)
    if cfg.signal.car40:
        data -= data.mean(axis=0, keepdims=True)
    sf = rec.sfreq
    start_off = round(cfg.window.tmin * sf)
    n_times = cfg.n_times
    boundaries = rec.event_samples[np.array(rec.event_codes) == "boundary"]
    by_code = cfg.label_by_code

    rows, dropped = [], []
    trials = assign_trials(rec.event_codes)
    for code, sample, trial in zip(rec.event_codes, rec.event_samples, trials, strict=True):
        if code not in by_code:
            continue
        s = int(sample) + start_off
        e = s + n_times
        reason = None
        if s < 0:
            reason = "before_start"
        elif e > data.shape[1]:
            reason = "past_end"
        # A boundary at sample b means a cut just before b; it splits [s, e) when s < b < e.
        elif cfg.window.drop_if_boundary_inside and np.any((boundaries > s) & (boundaries < e)):
            reason = "boundary_inside"
        if reason:
            dropped.append(
                {"file": path.name, "code": code, "trial_in_run": trial, "reason": reason}
            )
            continue
        rows.append((data[:, s:e], by_code[code].id, trial, s / sf))
    return rows, dropped


def build_session(subject: str, session: str, cfg: DataConfig, processed: Path) -> SessionWindows:
    runs = [
        r
        for r in list_processed_runs(processed)
        if r.subject == subject
        and r.session == session
        and not cfg.is_run_excluded(subject, session, r.run)
    ]
    if not runs:
        raise FileNotFoundError(f"No runs for {subject} {session}")
    X, y, uid, run_ids, tir, onset, dropped = [], [], [], [], [], [], []
    for r in sorted(runs, key=lambda r: r.run):
        rows, d = cut_run(r.path, cfg)
        dropped += d
        for x, label, trial, t0 in rows:
            X.append(x)
            y.append(label)
            run_ids.append(int(r.run))
            tir.append(trial)
            uid.append(f"{subject}_ses-{session}_run-{r.run}_trial-{trial:02d}")
            onset.append(t0)
    return SessionWindows(
        np.stack(X),
        np.asarray(y, np.int64),
        np.asarray(uid),
        np.asarray(run_ids, np.int8),
        np.asarray(tir, np.int16),
        np.asarray(onset, np.float64),
        dropped,
    )


def save_session(sw: SessionWindows, out: Path) -> str:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.npz")
    # Uncompressed: EEG is noise-like and barely compresses, and plain loads are faster.
    np.savez(
        tmp,
        X=sw.X,
        y=sw.y,
        trial_uid=sw.trial_uid,
        run=sw.run,
        trial_in_run=sw.trial_in_run,
        onset_s=sw.onset_s,
    )
    tmp.replace(out)
    return hashlib.sha256(out.read_bytes()).hexdigest()


def _settings(cfg: DataConfig) -> dict:
    return {
        "channels": list(cfg.channels.keep),
        "sfreq": cfg.signal.sfreq,
        "window": {"tmin": cfg.window.tmin, "tmax": cfg.window.tmax, "n_times": cfg.n_times},
        "switches": {
            "car40": cfg.signal.car40,
            "units": "volts",
            "drop_if_boundary_inside": cfg.window.drop_if_boundary_inside,
        },
        "excluded_sessions": sorted(f"{e.subject}/{e.session}" for e in cfg.exclusions.sessions),
        "excluded_runs": sorted(f"{e.subject}/{e.session}/{e.run}" for e in cfg.exclusions.runs),
    }


def build_all(
    cfg: DataConfig,
    processed: Path,
    out_dir: Path,
    subjects: list[str] | None = None,
    git_sha: str = "unknown",
) -> pd.DataFrame:
    """Cut and cache every (subject, session).

    With `subjects`, rebuild only those and keep the rest of an existing cache
    (refused if the existing cache used other settings).
    """
    if subjects is not None and not subjects:
        raise ValueError("subjects must be None (all) or a non-empty list")
    out_dir.mkdir(parents=True, exist_ok=True)
    settings = _settings(cfg)
    old_meta, old_drops, hashes = None, None, {}
    if subjects is not None and (out_dir / "manifest.json").exists():
        old = json.loads((out_dir / "manifest.json").read_text())
        if {k: old.get(k) for k in settings} != settings:
            raise RuntimeError(
                "Existing cache has other settings; rebuild everything (make epochs)."
            )
        old_meta = pd.read_parquet(out_dir / "metadata.parquet")
        old_meta = old_meta[~old_meta.subject.isin(subjects)]
        old_drops = pd.read_parquet(out_dir / "dropped.parquet")
        old_drops = old_drops[~old_drops.subject.isin(subjects)]
        hashes = {f: h for f, h in old["files"].items() if f.split("_ses-")[0] not in subjects}
    # Until the new manifest is written at the end, nothing can load a half-rebuilt cache.
    (out_dir / "manifest.json").unlink(missing_ok=True)
    meta, drops = [], []
    for subject in subjects if subjects is not None else cfg.subjects.ids:
        for session in cfg.sessions_for(subject):
            sw = build_session(subject, session, cfg, processed)
            name = f"{subject}_ses-{session}.npz"
            hashes[name] = save_session(sw, out_dir / name)
            for i in range(len(sw.y)):
                meta.append(
                    {
                        "subject": subject,
                        "session": session,
                        "run": int(sw.run[i]),
                        "trial_in_run": int(sw.trial_in_run[i]),
                        "trial_uid": sw.trial_uid[i],
                        "label": int(sw.y[i]),
                        "label_name": cfg.labels[int(sw.y[i])].name,
                        "group": subject_group(subject),
                        "hemiplegia_side": hemiplegia_side(subject),
                        "source_file": name,
                        "row_in_npz": i,
                    }
                )
            drops += [dict(d, subject=subject, session=session) for d in sw.dropped]
            log.info("%s %s: %d windows, %d dropped", subject, session, len(sw.y), len(sw.dropped))
    frames = [f for f in (old_meta, pd.DataFrame(meta)) if f is not None and len(f)]
    md = pd.concat(frames, ignore_index=True)
    drop_frames = [f for f in (old_drops, pd.DataFrame(drops, columns=DROP_COLS)) if f is not None]
    dr = pd.concat(drop_frames, ignore_index=True)
    md = md.sort_values(["subject", "source_file", "row_in_npz"], kind="stable", ignore_index=True)
    md.to_parquet(out_dir / "metadata.parquet", index=False)
    dr.to_parquet(out_dir / "dropped.parquet", index=False)
    manifest = {
        **settings,
        "package_version": __version__,
        "git_sha": git_sha,
        "n_windows": len(md),
        "n_dropped": len(dr),
        "files": dict(sorted(hashes.items())),
    }
    tmp = out_dir / "manifest.json.tmp"
    tmp.write_text(json.dumps(manifest, indent=2))
    tmp.replace(out_dir / "manifest.json")
    return md


def manifest_sha(out_dir: Path) -> str:
    return hashlib.sha256((out_dir / "manifest.json").read_bytes()).hexdigest()[:16]


def load_windows(
    out_dir: Path,
    cfg: DataConfig,
    subjects: list[str] | None = None,
    sessions: list[str] | None = None,
    labels: list[int] | None = None,
    mirror: bool = False,
) -> tuple[np.ndarray, pd.DataFrame]:
    """Windows and their metadata rows, in a stable order.

    Returns X: (n, 40, n_times) float32 volts and the matching metadata frame, whose
    index is 0..n-1 (row i of the frame is X[i]).
    """
    manifest = json.loads((out_dir / "manifest.json").read_text())
    expected = _settings(cfg)
    diff = [k for k in expected if manifest.get(k) != expected[k]]
    if diff:
        raise RuntimeError(f"Epoch cache was built with different {diff}; run `make epochs` again.")
    md = pd.read_parquet(out_dir / "metadata.parquet")
    n_rows = md.source_file.value_counts()
    if subjects is not None:
        md = md[md.subject.isin(subjects)]
    if sessions is not None:
        md = md[md.session.isin(sessions)]
    if labels is not None:
        md = md[md.label.isin(labels)]
    if md.empty:
        raise ValueError("No cached windows match the selection.")
    parts = []
    for name, rows in md.groupby("source_file", sort=True):
        with np.load(out_dir / name) as npz:
            stored = npz["X"]
            # A rebuild that stopped halfway leaves new files under old metadata.
            if stored.shape[0] != n_rows[name]:
                raise RuntimeError(
                    f"{name} holds {stored.shape[0]} windows but the metadata lists "
                    f"{n_rows[name]}; run `make epochs` again."
                )
            X = stored[rows.row_in_npz.to_numpy()]
        if mirror:
            X = mirror_if_needed(X, rows.subject.iloc[0], cfg.channels.keep)
        parts.append((X, rows))
    X = np.concatenate([p[0] for p in parts])
    md = pd.concat([p[1] for p in parts], ignore_index=True)
    return X, md
