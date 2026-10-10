"""Summarise the P07 deep-learning baselines (descriptive: no hypothesis rests on them).

uv run python scripts/summarise_dl.py

1. EEGNet trained on one session only (results/runs/dl_baselines): per-subject mean over
   folds and seeds, group mean with a bootstrap CI, next to the classical methods on the
   same run-level splits (results/summary/rq1_subject_values.csv).
2. The leave-one-subject-out pre-training (models/pretrained/manifest.json): epochs, best
   validation loss and the learning curves of three models.
3. Zero-shot (P07 step 4.5): each pre-trained model on its own target's runs 03-04, aligned
   with the declared k = 0 set (the REST windows of runs 01-02, protocol 4.2), session pre.
"""

from __future__ import annotations

import argparse
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
COMPARE = ["csp_lda", "ts_lr"]


def baselines(runs: Path, summary: Path) -> pd.DataFrame:
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
    classical = pd.read_csv(summary / "rq1_subject_values.csv")
    classical = classical[
        classical.method.isin(COMPARE)
        & (classical.feature == "bandpower")
        & (classical.session == "pre")
        & classical.protocol.isin(["loro", "chrono"])
    ]
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


def pretraining(models: Path, summary: Path, audit: Path, figures: Path) -> None:
    manifest_path = models / "manifest.json"
    if not manifest_path.exists():
        log.warning("no pre-training manifest yet")
        return
    # The Kaggle manifest predates write_manifest's trailing newline; the hook wants one.
    (audit / "pretrain_manifest.json").write_text(manifest_path.read_text().rstrip("\n") + "\n")
    m = json.loads(manifest_path.read_text())
    rows = [
        {k: e[k] for k in ("file", "target", "epochs_run", "best_epoch", "best_valid_loss",
                           "n_train_windows", "n_valid_windows", "seconds", "device", "torch")}
        | {"validation_subjects": ",".join(e["validation_subjects"])}
        for e in m.values()
    ]  # fmt: skip
    pd.DataFrame(rows).to_csv(summary / "dl_pretrain_table.csv", index=False, float_format="%.6g")
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


def figure(sv: pd.DataFrame, zs: pd.DataFrame | None, summary: Path, figures: Path) -> None:
    classical = pd.read_csv(summary / "rq1_subject_values.csv")
    classical = classical[
        classical.method.isin(COMPARE) & (classical.feature == "bandpower")
        & (classical.session == "pre") & (classical.protocol == "loro")
    ]  # fmt: skip
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
    sv = baselines(paths.results / "runs", summary)
    pretraining(args.models, summary, audit, figures)
    zs = zero_shot(args.models, summary)
    figure(sv, zs, summary, figures)
    log.info("dl summaries in %s", summary)


if __name__ == "__main__":
    main()
