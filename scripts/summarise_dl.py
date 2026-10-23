"""Summarise the P07 deep-learning baselines (descriptive: no hypothesis rests on them).

uv run python scripts/summarise_dl.py

1. EEGNet trained on one session only (results/runs/dl_baselines): per-subject mean over
   folds and seeds, group mean with a bootstrap CI, next to the classical methods on the
   same run-level splits (the raw RQ1 folds in results/runs/rq1_*).
2. The leave-one-subject-out pre-training (models/pretrained/manifest.json): epochs, best
   validation loss, the learning curves of three models and a checksum of every weight file.
3. Zero-shot (P07 step 4.5): each pre-trained model on its own target's runs 03-04, aligned
   with the declared k = 0 set (the REST windows of runs 01-02, protocol 4.2), session pre;
   paired with the `chrono` results, which test on exactly the same windows.
4. The group numbers the text quotes (dl_summary.json): the seed-to-seed spread, the
   pre-training's time, device and median best epoch, the zero-shot alignment's rest windows;
   and each class's recall (dl_class_recall.csv) from the fold confusion matrices.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import balanced_accuracy_score

from sixthfinger.config import load_data_config, load_protocol_config
from sixthfinger.data.epochs import load_windows
from sixthfinger.evaluation.runner import method_params
from sixthfinger.evaluation.stats import paired_test
from sixthfinger.evaluation.summary import describe, subject_values
from sixthfinger.models.deep import build_module, pretrained_name
from sixthfinger.paths import get_paths
from sixthfinger.preprocessing.alignment import align, reference_matrix
from sixthfinger.viz.plots import ACCENT, save, use_style

log = logging.getLogger("dl")
TASKS = {"T1_ah_vs_sf": (1, 2), "T2_rest_ah_sf": (0, 1, 2), "T3_sf_vs_rest": (0, 2)}
CLASS_NAMES = {0: "rest", 1: "affected_hand", 2: "sixth_finger"}
COMPARE = ["csp_lda", "ts_lr"]
CLASSICAL = ["csp_lda", "csp_svm", "fbcsp_lda", "mdm", "ts_lr"]


def classical_values(runs: Path) -> pd.DataFrame:
    """CSP+LDA and TS+LR per subject, `pre`, from the raw RQ1 folds at full precision.

    The committed rq1_subject_values.csv keeps 6 significant figures, enough to reorder two
    near-tied differences in a Wilcoxon test (T1 `loro`: p 0.566 instead of 0.545).
    """
    s = pd.concat(
        [pd.read_parquet(runs / n / "scores.parquet") for n in ("rq1_benchmark", "rq1_context")],
        ignore_index=True,
    )
    s = s[
        s.method.isin(COMPARE)
        & (s.feature == "bandpower")
        & (s.session == "pre")
        & s.protocol.isin(["loro", "chrono"])
    ]
    unit = ["task", "method", "protocol", "subject", "session"]
    parts = [subject_values(rows, unit, len(TASKS[t])) for t, rows in s.groupby("task")]
    return pd.concat(parts, ignore_index=True)


def baselines(runs: Path, summary: Path, classical: pd.DataFrame) -> pd.DataFrame:
    scores = pd.read_parquet(runs / "dl_baselines" / "scores.parquet")
    unit = ["task", "method", "protocol", "subject", "session", "draw"]
    per_seed = pd.concat(
        [subject_values(rows, unit, len(TASKS[task])) for task, rows in scores.groupby("task")],
        ignore_index=True,
    )
    sv = per_seed.groupby(["task", "method", "protocol", "subject", "session"], as_index=False).agg(
        bal_acc=("bal_acc", "mean"), seed_sd=("bal_acc", "std"), n_seeds=("draw", "nunique")
    )
    sv.to_csv(summary / "dl_baselines_subject_values.csv", index=False, float_format="%.6g")
    rows = []
    for (task, protocol), g in sv.groupby(["task", "protocol"]):
        d = describe(g.bal_acc)
        row = dict(task=task, protocol=protocol, method="eegnet_scratch", **d,
                   chance=1 / len(TASKS[task]), mean_seed_sd=float(g.seed_sd.mean()))  # fmt: skip
        rows.append(row)
        for m in COMPARE:
            c = classical[(classical.task == task) & (classical.protocol == protocol)]
            c = c[c.method == m].set_index("subject").bal_acc
            both = pd.concat([g.set_index("subject").bal_acc.rename("e"), c.rename("c")], axis=1)
            both = both.dropna()
            res = paired_test(both.e.to_numpy(), both.c.to_numpy())
            rows.append(dict(task=task, protocol=protocol, method=m, **describe(c),
                             chance=1 / len(TASKS[task]),
                             eegnet_minus_points=res["mean_diff"] * 100,
                             diff_ci_lo_points=res["ci_lo"] * 100,
                             diff_ci_hi_points=res["ci_hi"] * 100,
                             paired_p_two_sided=res["p"], paired_n=res["n"]))  # fmt: skip
    table = pd.DataFrame(rows)
    table.to_csv(summary / "dl_baselines_table.csv", index=False, float_format="%.6g")
    return sv


def class_recall(runs: Path) -> pd.DataFrame:
    """Each class's recall, `pre`, `loro` and `chrono`: per fold from its confusion matrix (rows
    are the true classes in the task's order), averaged over folds and seeds per patient, then
    over patients; EEGNet trained on one patient and the five classical methods."""
    deep = pd.read_parquet(runs / "dl_baselines" / "scores.parquet")
    classical = pd.concat(
        [pd.read_parquet(runs / n / "scores.parquet") for n in ("rq1_benchmark", "rq1_context")],
        ignore_index=True,
    )
    classical = classical[classical.method.isin(CLASSICAL) & (classical.feature == "bandpower")]
    s = pd.concat([deep, classical], ignore_index=True)
    s = s[(s.session == "pre") & s.protocol.isin(["loro", "chrono"]) & s.confusion.notna()]
    rows = []
    for r in s.itertuples():
        cm = np.array(json.loads(r.confusion), dtype=float)
        with np.errstate(invalid="ignore", divide="ignore"):
            recall = cm.diagonal() / cm.sum(axis=1)
        for label, value in zip(TASKS[r.task], recall, strict=True):
            rows.append(dict(task=r.task, method=r.method, protocol=r.protocol, subject=r.subject,
                             cls=CLASS_NAMES[label], recall=value))  # fmt: skip
    per = pd.DataFrame(rows).groupby(["task", "method", "protocol", "cls", "subject"]).recall.mean()
    out = per.groupby(["task", "method", "protocol", "cls"]).agg(["size", "mean"])
    out = out.rename(columns={"size": "n", "mean": "mean_recall"}).reset_index()
    return out.rename(columns={"cls": "class"})


def group_numbers(sv: pd.DataFrame, summary: Path, kaggle_job: Path) -> dict:
    """The numbers the text quotes about the baselines that no other table states."""
    pretrain = pd.read_csv(summary / "dl_pretrain_table.csv")
    zero = pd.read_csv(summary / "dl_zeroshot_subject_values.csv")
    reference = zero.drop_duplicates("subject").n_reference
    job = json.loads(kaggle_job.read_text()) if kaggle_job.exists() else {}
    job_minutes = job["seconds"] / 60 if "seconds" in job else None
    return {
        "seed SD per patient, task and protocol (points)": {
            "rows": int(sv.seed_sd.notna().sum()),
            "mean": float(100 * sv.seed_sd.mean()),
            "median": float(100 * sv.seed_sd.median()),
            "max": float(100 * sv.seed_sd.max()),
        },
        "pre-training": {
            "models": len(pretrain),
            "training minutes, sum over the models": float(pretrain.seconds.sum() / 60),
            "training seconds per model, median": float(pretrain.seconds.median()),
            "best epoch, median": float(pretrain.best_epoch.median()),
            "devices": sorted(set(pretrain.device)),
            "device name (Kaggle job)": job.get("device_name"),
            "job minutes (Kaggle job, wall clock)": job_minutes,
        },
        "zero-shot alignment, rest windows per patient": {
            "patients": len(reference),
            "median": float(reference.median()),
            "min": int(reference.min()),
            "max": int(reference.max()),
        },
    }


def pretraining(models: Path, summary: Path, audit: Path, figures: Path | None) -> None:
    manifest_path = models / "manifest.json"
    if not manifest_path.exists():
        log.warning("no pre-training manifest yet")
        return
    # The Kaggle manifest predates write_manifest's trailing newline; the hook wants one.
    (audit / "pretrain_manifest.json").write_text(manifest_path.read_text().rstrip("\n") + "\n")
    every = json.loads(manifest_path.read_text())
    # The weights are not in git; their checksums tie the committed results to them, the
    # no-signal (permuted) models included. The table and the figure are the real models only.
    sums = [
        dict(file=f, bytes=(models / f).stat().st_size,
             sha256=hashlib.sha256((models / f).read_bytes()).hexdigest())
        for f in sorted(every) if (models / f).exists()
    ]  # fmt: skip
    pd.DataFrame(sums).to_csv(audit / "pretrained_weights.csv", index=False)
    m = {f: e for f, e in every.items() if not e.get("permuted")}
    rows = [
        {k: e[k] for k in ("file", "target", "epochs_run", "best_epoch", "best_valid_loss",
                           "n_train_windows", "n_valid_windows", "seconds", "device", "torch")}
        | {"validation_subjects": ",".join(e["validation_subjects"])}
        for e in m.values()
    ]  # fmt: skip
    pd.DataFrame(rows).to_csv(summary / "dl_pretrain_table.csv", index=False, float_format="%.6g")
    if figures is None:
        return
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.4), sharey=True)
    for ax, e in zip(axes, list(m.values())[:3], strict=False):
        h = pd.DataFrame(e["history"])
        ax.plot(h.epoch, h.train_loss, color="0.5", lw=1, label="train")
        ax.plot(h.epoch, h.valid_loss, color=ACCENT, lw=1.5, label="validation subjects")
        ax.axvline(e["best_epoch"], color="k", lw=0.6, ls=":")
        ax.set_title(f"target {e['target']}", fontsize=8)
        ax.set_xlabel("epoch")
    axes[0].set_ylabel("cross-entropy")
    axes[0].legend(frameon=False, fontsize=7)
    save(fig, figures, "dl_pretrain_curves")


def zero_shot(models: Path, summary: Path) -> pd.DataFrame | None:
    paths, data_cfg, proto = get_paths(), load_data_config(), load_protocol_config()
    cfg = method_params("eegnet_ea_ft", paths.configs)
    pool, test = proto.calibration.pool_runs, proto.calibration.test_runs
    rows = []
    for target in data_cfg.subjects.ids:
        weights = models / pretrained_name(target, mirror=False, aligned=True)
        if "pre" not in data_cfg.sessions_for(target) or not weights.exists():
            continue
        X, md = load_windows(paths.epochs, data_cfg, subjects=[target], sessions=["pre"])
        runs = md.run.astype(int).map("{:02d}".format)
        ref = ((md.label == 0) & runs.isin(pool)).to_numpy()  # the declared k = 0 set
        te = runs.isin(test).to_numpy()
        net = build_module(cfg, X.shape[1], 3, X.shape[2])
        net.load_state_dict(torch.load(weights, weights_only=True, map_location="cpu"))
        net.eval()
        x = align(X[te], reference_matrix(X[ref])) * cfg["input_scale"]
        with torch.no_grad():
            proba = torch.softmax(net(torch.from_numpy(x.astype(np.float32))), dim=1).numpy()
        y = md.label.to_numpy()[te]
        for task, classes in TASKS.items():
            keep = np.isin(y, classes)
            p = proba[keep][:, list(classes)]  # the task's columns, renormalised
            pred = np.asarray(classes)[p.argmax(axis=1)]
            rows.append(dict(task=task, subject=target, session="pre", n_test=int(keep.sum()),
                             n_reference=int(ref.sum()),
                             bal_acc=balanced_accuracy_score(y[keep], pred)))  # fmt: skip
    if not rows:
        log.warning("no pre-trained models found for zero-shot")
        return None
    zs = pd.DataFrame(rows)
    zs.to_csv(summary / "dl_zeroshot_subject_values.csv", index=False, float_format="%.6g")
    table = pd.DataFrame(
        [
            dict(task=t, **describe(g.bal_acc), chance=1 / len(TASKS[t]))
            for t, g in zs.groupby("task")
        ]
    )
    table.to_csv(summary / "dl_zeroshot_table.csv", index=False, float_format="%.6g")
    return zs


def zero_shot_paired(
    zs: pd.DataFrame, sv: pd.DataFrame, classical: pd.DataFrame, summary: Path
) -> None:
    """Zero-shot minus each `chrono` result: both test on runs 03-04 of `pre`, window for window.

    `chrono` trains on the labelled runs 01-02; zero-shot uses only their REST windows,
    unlabelled, for the alignment. Two-sided Wilcoxon, descriptive (no correction).
    """
    chrono = pd.concat([sv[sv.protocol == "chrono"], classical[classical.protocol == "chrono"]])
    rows = []
    for (task, method), g in chrono.groupby(["task", "method"]):
        both = pd.concat(
            [
                zs[zs.task == task].set_index("subject").bal_acc.rename("z"),
                g.set_index("subject").bal_acc.rename("c"),
            ],
            axis=1,
        ).dropna()
        res = paired_test(both.z.to_numpy(), both.c.to_numpy())
        rows.append(
            dict(
                task=task,
                versus=method,
                protocol="chrono",
                n=res["n"],
                zero_shot_minus_points=res["mean_diff"] * 100,
                diff_ci_lo_points=res["ci_lo"] * 100,
                diff_ci_hi_points=res["ci_hi"] * 100,
                paired_p_two_sided=res["p"],
            )
        )
    out = pd.DataFrame(rows)
    out.to_csv(summary / "dl_zeroshot_paired.csv", index=False, float_format="%.6g")


def figure(
    sv: pd.DataFrame, zs: pd.DataFrame | None, classical: pd.DataFrame, figures: Path
) -> None:
    classical = classical[classical.protocol == "loro"]
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.8))
    for ax, (task, classes) in zip(axes, TASKS.items(), strict=True):
        groups = [("EEGNet\nscratch", sv[(sv.task == task) & (sv.protocol == "loro")].bal_acc)]
        groups += [(m, classical[(classical.task == task) & (classical.method == m)].bal_acc)
                   for m in COMPARE]  # fmt: skip
        if zs is not None:
            groups.append(("EEGNet\nzero-shot", zs[zs.task == task].bal_acc))
        for i, (_, v) in enumerate(groups):
            ax.boxplot(v, positions=[i], widths=0.5, showfliers=False)
            jitter = np.random.default_rng(i).uniform(-0.12, 0.12, len(v))
            ax.plot(i + jitter, v, ".", color="0.35", ms=3)
        ax.axhline(1 / len(classes), color="0.5", lw=0.8)
        ax.set_xticks(range(len(groups)), [g[0] for g in groups], fontsize=7)
        ax.set_title(f"{task.split('_', 1)[1].replace('_', ' ')} (pre)", fontsize=8)
    axes[0].set_ylabel("balanced accuracy")
    fig.suptitle("Leave-run-out (zero-shot: runs 03-04 only)", fontsize=8, y=1.02)
    save(fig, figures, "dl_baselines")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--models", type=Path, default=Path("models/pretrained"))
    ap.add_argument("--kaggle-job", type=Path, default=Path("results/kaggle/pretrain/job.json"),
                    help="the pre-training job's record, for the GPU's name")  # fmt: skip
    ap.add_argument("--no-figures", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("fontTools").setLevel(logging.WARNING)
    use_style()
    paths = get_paths()
    summary, audit, figures = (
        paths.results / "summary",
        paths.audit,
        paths.root / "docs" / "figures",
    )
    classical = classical_values(paths.results / "runs")
    sv = baselines(paths.results / "runs", summary, classical)
    pretraining(args.models, summary, audit, None if args.no_figures else figures)
    zs = zero_shot(args.models, summary)
    if zs is not None:
        zero_shot_paired(zs, sv, classical, summary)
    recall = class_recall(paths.results / "runs")
    recall.to_csv(summary / "dl_class_recall.csv", index=False, float_format="%.6g")
    numbers = group_numbers(sv, summary, args.kaggle_job)
    (summary / "dl_summary.json").write_text(json.dumps(numbers, indent=2) + "\n")
    if not args.no_figures:
        figure(sv, zs, classical, figures)
    log.info("dl summaries in %s", summary)


if __name__ == "__main__":
    main()
