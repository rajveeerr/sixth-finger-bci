"""Explain the P08 sanity check against P06: refit both training sets for every pair.

uv run python scripts/check_calibration_sanity.py

S1 at k = all (T2) takes every trial with its REST window (pre-registration 3.4); P06's
`chrono` trained on every window of runs 01-02, including the REST windows of trials whose
imagery window was dropped (P03). For each subject and method of the check, refit on both
sets and score runs 03-04: the S1 set must give the P08 value and the full pool the P06
value. Writes results/audit/calib_sanity_refit.csv.
"""

from __future__ import annotations

import pandas as pd

from sixthfinger.config import load_data_config
from sixthfinger.data.epochs import load_windows
from sixthfinger.evaluation.calibration import draw_calibration_set
from sixthfinger.evaluation.metrics import score
from sixthfinger.evaluation.runner import method_params, task_windows
from sixthfinger.models.registry import Batch, make_method
from sixthfinger.paths import current_git_sha, get_paths

CLASSES = [0, 1, 2]


def refit(method: str, params: dict, X, train: pd.DataFrame, test: pd.DataFrame) -> float:
    m = make_method(method, n_classes=3, **params)
    m.fit(Batch(X[train.index], train.label.to_numpy(), train))
    return score(test.label.to_numpy(), m.predict_proba(X[test.index]), CLASSES)["bal_acc"]


def main() -> None:
    paths, data_cfg = get_paths(), load_data_config()
    check = pd.read_csv(paths.results / "summary" / "calib_sanity_vs_p06.csv")
    rows = []
    for subject, g in check.groupby("subject"):
        X, md = load_windows(paths.epochs, data_cfg, subjects=[subject], sessions=["pre"])
        md = md.reset_index(drop=True)
        pool, test = md[md.run.isin([1, 2])], md[md.run.isin([3, 4])]
        cd = draw_calibration_set(pool, [], [1, 2], 20, "0", k_all=20)
        s1 = task_windows(pool.iloc[cd.labelled_idx], CLASSES)
        orphans = pool[~pool.index.isin(s1.index)]
        for r in g.itertuples():
            params = method_params(r.method, paths.configs)
            rows.append(dict(subject=subject, method=r.method, p08=r.p08, p06=r.p06,
                             n_s1=len(s1), n_pool=len(pool), n_orphan_rest=len(orphans),
                             orphan_labels=",".join(map(str, sorted(set(orphans.label)))),
                             refit_s1=refit(r.method, params, X, s1, test),
                             refit_pool=refit(r.method, params, X, pool, test)))  # fmt: skip
    out = pd.DataFrame(rows)
    out["s1_reproduces_p08"] = (out.refit_s1 - out.p08).abs() < 1e-6
    out["pool_reproduces_p06"] = (out.refit_pool - out.p06).abs() < 1e-6
    out["git_sha"] = current_git_sha()
    out.to_csv(paths.audit / "calib_sanity_refit.csv", index=False, float_format="%.6g")
    print(
        f"{len(out)} pairs; S1 set gives P08: {out.s1_reproduces_p08.all()}; "
        f"pool gives P06: {out.pool_reproduces_p06.all()}; "
        f"orphan REST windows per session: {sorted(set(out.n_orphan_rest))}"
    )


if __name__ == "__main__":
    main()
