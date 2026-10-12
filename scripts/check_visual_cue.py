"""P09 Study 5, point 5: could REST vs imagery be decoded from what the patient sees?

uv run python scripts/check_visual_cue.py

REST windows are recorded with a fixation cross on screen, imagery windows with a picture
cue. `ts_lr` under `chrono` (train runs 01-02, test runs 03-04, `pre`) is fitted on the full
montage, on the five parieto-occipital channels alone and on the 14 central channels alone,
for SF vs REST and AH vs SF. The full montage must reproduce P06's `chrono` value for every
patient, which checks the windows. Exploratory, added after the P08 results.
Writes results/summary/rq4_visual_cue_decode.csv (per patient) and _table.csv.
"""

from __future__ import annotations

import pandas as pd

from sixthfinger.config import load_data_config
from sixthfinger.data.epochs import load_windows
from sixthfinger.evaluation.metrics import score
from sixthfinger.evaluation.runner import method_params, task_windows
from sixthfinger.evaluation.stats import bootstrap_ci
from sixthfinger.models.registry import Batch, make_method
from sixthfinger.paths import current_git_sha, get_paths

CHANNEL_SETS = {
    "all_40": None,
    "parieto_occipital_5": ["POz", "PO3", "PO4", "PO5", "PO6"],
    "central_14": ["C1", "C2", "C3", "C4", "C5", "C6", "Cz",
                   "CP1", "CP2", "CP3", "CP4", "CP5", "CP6", "CPz"],
}  # fmt: skip
TASKS = {"T3_sf_vs_rest": [0, 2], "T1_ah_vs_sf": [1, 2]}


def decode(X, md: pd.DataFrame, classes: list[int], channels: list[int] | None) -> float:
    pool, test = md[md.run.isin([1, 2])], md[md.run.isin([3, 4])]
    train, test = task_windows(pool, classes), task_windows(test, classes)
    Xc = X if channels is None else X[:, channels]
    m = make_method("ts_lr", n_classes=2, **method_params("ts_lr", get_paths().configs))
    m.fit(Batch(Xc[train.index], train.label.to_numpy(), train))
    return score(test.label.to_numpy(), m.predict_proba(Xc[test.index]), classes)["bal_acc"]


def main() -> None:
    paths, cfg = get_paths(), load_data_config()
    names = list(cfg.channels.keep)
    p06 = pd.concat([pd.read_parquet(paths.runs / e / "scores.parquet")
                     for e in ("rq1_benchmark", "rq1_context")])  # fmt: skip
    p06 = p06[(p06.method == "ts_lr") & (p06.protocol == "chrono") & (p06.session == "pre")]
    p06 = p06.set_index(["subject", "task"]).bal_acc
    _, md_all = load_windows(paths.epochs, cfg, sessions=["pre"])
    rows = []
    for subject in sorted(md_all.subject.unique()):
        X, md = load_windows(paths.epochs, cfg, subjects=[subject], sessions=["pre"])
        md = md.reset_index(drop=True)
        for task, classes in TASKS.items():
            for set_name, chans in CHANNEL_SETS.items():
                idx = None if chans is None else [names.index(c) for c in chans]
                rows.append(dict(subject=subject, task=task, channels=set_name,
                                 n_channels=len(names) if idx is None else len(idx),
                                 bal_acc=decode(X, md, classes, idx)))  # fmt: skip
    out = pd.DataFrame(rows)
    full = out[out.channels == "all_40"].set_index(["subject", "task"]).bal_acc
    gap = (full - p06[full.index]).abs().max()
    print(f"full montage vs P06 chrono ts_lr: {len(full)} cells, largest difference {gap:.2e}")
    if gap > 1e-6:
        raise SystemExit("the full montage does not reproduce P06: the windows differ")
    out["git_sha"] = current_git_sha()
    summary = paths.results / "summary"
    out.to_csv(summary / "rq4_visual_cue_decode.csv", index=False, float_format="%.6g")
    table = []
    for (task, set_name), g in out.groupby(["task", "channels"]):
        mean, lo, hi = bootstrap_ci(g.bal_acc.to_numpy())
        table.append(dict(task=task, channels=set_name, n=len(g), mean=mean, ci_lo=lo, ci_hi=hi))
    table = pd.DataFrame(table)
    table.to_csv(summary / "rq4_visual_cue_table.csv", index=False, float_format="%.6g")
    print(table.to_string(index=False))


if __name__ == "__main__":
    main()
