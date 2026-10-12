"""Build the demo bundle (P10 step 4.4): the demo patient's whole held-out trials, the
exported decoder and its offline predictions, in the format `server/app/bundle.py` reads.

The choice follows rules fixed before the bundle was built (protocol §10; deviation log and
`DECISIONS.md` 60, 2026-10-12): the method named in `results/summary/calib_demo_method.csv`;
the patient whose P07 `chrono` three-class accuracy of that method is closest to the cohort
median, a tie broken by the share of whole held-out trials, then by the lower accuracy, then
by the subject id. The model is fitted by the P08 runner itself (S1, three classes, k = all,
seed 0) on runs 01-02; the bundle holds the trials of runs 03-04 with no boundary cut
between rest onset and cue + 6 s.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from sixthfinger.config import DataConfig, load_data_config, load_protocol_config
from sixthfinger.data.epochs import assign_trials, load_windows, run_signal
from sixthfinger.data.loading import list_processed_runs
from sixthfinger.evaluation.calibration import draw_calibration_set
from sixthfinger.evaluation.metrics import score
from sixthfinger.evaluation.runner import run_experiment, task_windows
from sixthfinger.export.onnx_export import export_onnx, onnx_probabilities
from sixthfinger.paths import current_git_sha, get_paths

CLASSES = [
    {"id": 0, "name": "rest", "label": "Rest", "command": "IDLE"},
    {"id": 1, "name": "affected_hand", "label": "Affected hand", "command": "HAND_GRASP"},
    {"id": 2, "name": "sixth_finger", "label": "Sixth finger", "command": "SIXTH_FINGER_FLEX"},
]
DISPLAY_CHANNELS = ["FC3", "C3", "CP3", "Cz", "FC4", "C4", "CP4"]
SCALE_UV = 0.01  # int16 steps of 0.01 µV: ±327 µV
TRIAL_END_S = 6.0  # a trial runs from rest onset to cue + 6 s (end of the imagery period)
EXPERIMENT = "demo_model"
SOURCE = {
    "dataset": (
        'Wang et al., "A multi-paradigm and longitudinal EEG dataset including the '
        '"sixth-finger" and "affected-hand" motor imagery of stroke patients", '
        "Scientific Data 13, 1109 (2026)"
    ),
    "doi": "10.1038/s41597-026-07787-y",
    "license": "CC BY 4.0",
}


def server_module(name: str):
    """A module of the server package (not installed in this environment), by path."""
    root = str(get_paths().root / "server")
    if root not in sys.path:
        sys.path.insert(0, root)
    return __import__(f"app.{name}", fromlist=["app"])


def trial_spans(codes: np.ndarray, samples: np.ndarray, sfreq: float, n_times: int) -> list:
    """Every trial of a run that has both its rest marker and its imagery cue, numbered as
    the epoch cache numbers them; `whole` when [rest onset, cue + 6 s) lies inside the run
    with no boundary cut in it."""
    codes = np.asarray(codes)
    boundaries = np.asarray(samples)[codes == "boundary"]
    events: dict[int, dict[str, int]] = {}
    for code, sample, trial in zip(codes, samples, assign_trials(list(codes)), strict=True):
        if trial:
            events.setdefault(trial, {})[str(code)] = int(sample)
    out = []
    for trial, ev in sorted(events.items()):
        cue_codes = [c for c in ev if c in ("2", "3")]
        if "1" not in ev or not cue_codes:
            continue
        start, cue = ev["1"], ev[cue_codes[0]]
        stop = cue + round(TRIAL_END_S * sfreq)
        whole = stop <= n_times and not ((boundaries > start) & (boundaries < stop)).any()
        out.append(dict(trial=trial, code=cue_codes[0], start=start, cue=cue, stop=stop,
                        whole=bool(whole)))  # fmt: skip
    return out


def held_out_trials(subject: str, cfg: DataConfig, runs: list[str]) -> tuple[list[dict], int]:
    """The whole trials of `runs` of the subject's `pre` session in µV, and the number of
    trials before the whole-trial rule."""
    kept, total = [], 0
    for r in list_processed_runs(get_paths().processed):
        if r.subject != subject or r.session != "pre" or r.run not in runs:
            continue
        if cfg.is_run_excluded(subject, "pre", r.run):
            continue
        data_v, rec = run_signal(r.path, cfg)
        spans = trial_spans(np.array(rec.event_codes), rec.event_samples, rec.sfreq,
                            data_v.shape[1])  # fmt: skip
        total += len(spans)
        for sp in (s for s in spans if s["whole"]):
            kept.append({
                **sp, "run": r.run, "sfreq": rec.sfreq,
                "uid": f"{subject}_ses-pre_run-{r.run}_trial-{sp['trial']:02d}",
                "label": cfg.label_by_code[sp["code"]].id,
                "data_uv": data_v[:, sp["start"] : sp["stop"]] / cfg.signal.scale_to_volts,
            })  # fmt: skip
    return kept, total


def demo_subject(method: str, cfg: DataConfig, test_runs: list[str]) -> tuple[str, dict]:
    sv = pd.read_csv(get_paths().results / "summary" / "dl_baselines_subject_values.csv")
    g = sv[(sv.task == "T2_rest_ah_sf") & (sv.protocol == "chrono") & (sv.session == "pre")
           & (sv.method == method)].copy()  # fmt: skip
    median = float(g.bal_acc.median())
    g["distance"] = (g.bal_acc - median).abs().round(9)
    tied = g[g.distance == g.distance.min()].copy()
    whole = {}
    for s in tied.subject:
        trials, total = held_out_trials(s, cfg, test_runs)
        whole[s] = (len(trials), total)
    tied["whole_share"] = tied.subject.map(lambda s: whole[s][0] / whole[s][1])
    tied = tied.sort_values(["whole_share", "bal_acc", "subject"], ascending=[False, True, True])
    subject = str(tied.subject.iloc[0])
    return subject, {
        "rule": "protocol §10; ties: whole held-out trials, lower accuracy, subject id",
        "cohort_median_chrono": median,
        "candidates": [
            dict(
                subject=r.subject,
                chrono_bal_acc=r.bal_acc,
                whole_trials=whole[r.subject][0],
                trials=whole[r.subject][1],
            )
            for r in tied.itertuples()
        ],
    }


def fit_demo_model(subject: str, method: str):
    """The S1, k = all decoder of the P08 runner for this subject, and its trial-locked row."""
    fitted = {}
    cfg_path = get_paths().configs / "experiments" / f"{EXPERIMENT}.yaml"
    with tempfile.TemporaryDirectory() as tmp:
        out = run_experiment(cfg_path, subjects=[subject], methods=[method],
                             runs_dir=Path(tmp),
                             on_fitted=lambda key, m: fitted.update(model=m))  # fmt: skip
        row = pd.read_parquet(out).iloc[0].to_dict()
    return fitted["model"], row


def training_uids(subject: str, cfg: DataConfig, pool_runs: list[str]) -> set[str]:
    """The trial ids of the S1, k = all training set (P08's draw at k = all)."""
    _, md = load_windows(get_paths().epochs, cfg, subjects=[subject], sessions=["pre"])
    md = md.reset_index(drop=True)
    pool = md[md.run.isin([int(r) for r in pool_runs])]
    cd = draw_calibration_set(pool, [], [1, 2], 20, "0", k_all=20)
    return set(task_windows(pool.iloc[cd.labelled_idx], [0, 1, 2]).trial_uid)


def windows(trials: list[dict], sfreq: float) -> tuple[np.ndarray, np.ndarray]:
    """The [1, 5) s windows after each rest onset and cue (as cached), and their labels."""
    w0, w1 = round(1.0 * sfreq), round(5.0 * sfreq)
    xs, ys = [], []
    for t in trials:
        rest, cue = 0, t["cue"] - t["start"]
        xs += [t["data_uv"][:, rest + w0 : rest + w1], t["data_uv"][:, cue + w0 : cue + w1]]
        ys += [0, t["label"]]
    return np.stack(xs).astype(np.float32), np.array(ys)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def encode(trials: list[dict]) -> tuple[bytes, list[dict], int]:
    """int16 at SCALE_UV per step; the trial table with byte offsets; samples clipped."""
    blobs, table, offset, clipped = [], [], 0, 0
    for i, t in enumerate(trials):
        q = np.round(t["data_uv"] / SCALE_UV)
        clipped += int((np.abs(q) > 32767).sum())
        blob = np.clip(q, -32768, 32767).astype("<i2").tobytes(order="C")
        table.append(dict(index=i, uid=t["uid"], label=int(t["label"]),
                          cue_onset_s=round((t["cue"] - t["start"]) / t["sfreq"], 4),
                          n_samples=int(t["data_uv"].shape[1]), offset_bytes=offset))  # fmt: skip
        blobs.append(blob)
        offset += len(blob)
    return b"".join(blobs), table, clipped


def build_demo_bundle(out_dir: Path, summary_path: Path) -> dict:
    paths, cfg, proto = get_paths(), load_data_config(), load_protocol_config()
    if cfg.signal.car40:
        raise ValueError("the bundle has no re-referencing op: fold CAR40 into a spatial filter")
    pool_runs, test_runs = list(proto.calibration.pool_runs), list(proto.calibration.test_runs)
    choice = pd.read_csv(paths.results / "summary" / "calib_demo_method.csv")
    method = str(choice[choice.demo_method].method.iloc[0])
    if not method.startswith("eegnet_scratch"):
        raise ValueError(f"{method}: only a model without alignment exports as it is (step 4.6)")
    subject, rule = demo_subject(method, cfg, test_runs)
    model, row = fit_demo_model(subject, method)
    trials, n_total = held_out_trials(subject, cfg, test_runs)
    trained = training_uids(subject, cfg, pool_runs)
    if trained & {t["uid"] for t in trials}:
        raise AssertionError("a bundle trial was in the demo model's training set")
    sfreq = float(trials[0]["sfreq"])
    X_uv, y = windows(trials, sfreq)
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / "model.onnx"
    parity = export_onnx(model.clf.module_, model_path, X_uv.shape[1], X_uv.shape[2],
                         real=X_uv[:16])  # fmt: skip
    # End to end: the fitted method on volts against the exported file on µV.
    p_method = model.predict_proba(X_uv * cfg.signal.scale_to_volts)
    p_onnx = onnx_probabilities(model_path, X_uv)
    parity["max_abs_diff_method"] = float(np.abs(p_method - p_onnx).max())
    blob, table, clipped = encode(trials)
    (out_dir / "trials.bin").write_bytes(blob)
    manifest = {
        "schema_version": 1,
        "created_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "synthetic": False,
        "source": {
            **SOURCE,
            "subject": subject,
            "session": "pre",
            "runs": [int(r) for r in test_runs],
            "attribution": (
                f"EEG of {subject}, runs {', '.join(test_runs)} of the pre "
                "session (held out from training), from Wang et al. (2026), "
                "Scientific Data, CC BY 4.0. Preprocessed by the dataset "
                "authors; replayed, not recorded live."
            ),
        },
        "sfreq": sfreq,
        "channels": list(cfg.channels.keep),
        "display_channels": DISPLAY_CHANNELS,
        "display_decimation": 2,
        "units": "uV",
        "classes": CLASSES,
        "window": {"start_s": 1.0, "end_s": 5.0},
        "model": {
            "file": "model.onnx",
            "sha256": sha256_of(model_path),
            "input_name": "eeg",
            "output_name": "probs",
            "output": "probabilities",
            "n_channels": X_uv.shape[1],
            "n_times": X_uv.shape[2],
            "name": "EEGNet trained on the demo patient alone",
            "method": method,
            "trained_on": f"{subject} pre runs {', '.join(pool_runs)}, every trial (S1, k = all)",
            "notes": f"seed 0, P08 runner, code {current_git_sha()}",
        },
        "preprocessing": [{"op": "scale", "factor": 1.0}],  # µV in, as the network was trained
        "encoding": {"dtype": "int16", "scale_uv": SCALE_UV},
        "trials_file": "trials.bin",
        "trials_sha256": sha256_of(out_dir / "trials.bin"),
        "predictions_file": "predictions.json",
        "trials": table,
    }
    server_module("bundle").Manifest.model_validate(manifest)  # the server's schema decides
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    # Offline predictions from the stored (int16) trials, as the server and browser read them.
    bundle = server_module("bundle").Bundle(out_dir)
    stored = [dict(t, data_uv=bundle.trial_data(i)) for i, t in enumerate(trials)]
    X_stored, _ = windows(stored, sfreq)
    probs = onnx_probabilities(model_path, X_stored)
    items = [dict(trial=i // 2, window="rest" if i % 2 == 0 else "imagery",
                  probs=[round(float(v), 5) for v in p], label_id=int(np.argmax(p)))
             for i, p in enumerate(probs)]  # fmt: skip
    (out_dir / "predictions.json").write_text(json.dumps(
        {"schema_version": 1, "model_sha256": manifest["model"]["sha256"], "items": items},
        indent=1) + "\n")  # fmt: skip
    info = {
        "subject": subject, "method": method, "choice": rule,
        "trials_whole": len(trials), "trials_total": n_total, "clipped_samples": clipped,
        "held_out_bal_acc": score(y, probs, [0, 1, 2])["bal_acc"],
        "runner_row_bal_acc": float(row["bal_acc"]), "runner_row_n_test": int(row["n_test"]),
        "n_training_trials": len(trained), "parity": parity,
        "max_quantisation_error_uv": float(np.abs(X_stored - X_uv).max()),
        "bundle_bytes": sum(f.stat().st_size for f in out_dir.iterdir() if f.is_file()),
        "git_sha": current_git_sha(),
    }  # fmt: skip
    summary_path.write_text(json.dumps(info, indent=2) + "\n")
    return info
