"""Per-subject values, group tables and the paired leakage tests of RQ1 and RQ1b."""

from __future__ import annotations

from collections.abc import Callable, Iterable

import numpy as np
import pandas as pd

from sixthfinger.evaluation.metrics import chance_threshold
from sixthfinger.evaluation.stats import bootstrap_ci, holm, paired_test

WITHIN_PROTOCOLS = ["paper_replica", "cv_leakfree", "loro", "chrono"]
REPEATED_CV = ("paper_replica", "cv_leakfree")


def subject_values(scores: pd.DataFrame, unit: list[str], n_classes: int) -> pd.DataFrame:
    """Mean balanced accuracy over the folds of each unit, and whether it beats chance.

    scores: one row per fold (results contract, with n_folds). unit: the columns that
    identify a subject-session result, protocol included. A repeated CV tests every window
    once per repeat, so its test-set size is counted over the first repeat only.
    """
    first = scores[~scores.protocol.isin(REPEATED_CV) | (scores.fold < scores.n_folds)]
    out = scores.groupby(unit, as_index=False).agg(
        bal_acc=("bal_acc", "mean"),
        acc=("acc", "mean"),
        n_fits=("fold", "size"),
        n_folds=("n_folds", "first"),
    )
    tested = first.groupby(unit, as_index=False).agg(n_windows=("n_test", "sum"))
    out = out.merge(tested, on=unit, validate="one_to_one")
    out["chance_threshold"] = [chance_threshold(int(n), n_classes) for n in out.n_windows]
    out["above_chance"] = out.bal_acc > out.chance_threshold
    return out


def describe(values: Iterable[float]) -> dict:
    """n, mean, SD, median and the 95 % percentile bootstrap CI of the mean over subjects."""
    v = np.asarray(list(values), float)
    v = v[~np.isnan(v)]
    if not v.size:
        return dict(n=0, mean=np.nan, sd=np.nan, median=np.nan, ci_lo=np.nan, ci_hi=np.nan)
    mean, lo, hi = bootstrap_ci(v)
    sd = float(v.std(ddof=1)) if v.size > 1 else np.nan
    return dict(n=int(v.size), mean=mean, sd=sd, median=float(np.median(v)), ci_lo=lo, ci_hi=hi)


def merge_linked(values: pd.DataFrame, split_group: Callable[[str], str]) -> pd.DataFrame:
    """One row per independent group: linked subjects (sub-21, sub-22) averaged into one."""
    keys = [c for c in values.columns if c not in ("subject", "bal_acc", "acc")]
    grouped = values.assign(subject=values.subject.map(split_group))
    return grouped.groupby([*keys, "subject"], as_index=False, dropna=False)[
        ["bal_acc", "acc"]
    ].mean()


def paired(
    wide: pd.DataFrame, a: str, b: str, alternative: str = "two-sided", scale: float = 100.0
) -> dict:
    """Wilcoxon of column a minus column b over the rows (subjects) where both exist.

    Differences and their CI are multiplied by `scale` (points of balanced accuracy).
    """
    # A protocol whose cells are all declared missing (Cho2017 chrono) has no column at all
    # after pivot_table; it is a comparison with no pairs, not an error.
    both = wide.reindex(columns=[a, b]).dropna()
    if both.empty:
        nan = float("nan")
        return {
            "n": 0,
            "n_nonzero": 0,
            "median_diff": nan,
            "mean_diff": nan,
            "ci_lo": nan,
            "ci_hi": nan,
            "W": nan,
            "p": nan,
            "r_rb": nan,
            "alternative": alternative,
        }
    res = paired_test(both[a].to_numpy(), both[b].to_numpy(), alternative=alternative)
    for k in ("median_diff", "mean_diff", "ci_lo", "ci_hi"):
        res[k] *= scale
    return res


def holm_family(pvals: dict[str, float | None]) -> dict[str, float]:
    """Holm-adjusted p for every declared member; a member that was not run counts as p = 1.

    Keeping the declared family size means dropping a member never makes the rest less
    corrected than planned.
    """
    names = list(pvals)
    raw = [1.0 if pvals[n] is None or np.isnan(pvals[n]) else float(pvals[n]) for n in names]
    _, adj = holm(raw)
    return dict(zip(names, (float(p) for p in adj), strict=True))


def one_sided_category(p: float, alpha: float = 0.05) -> str:
    """Pre-registration 5.1 for a one-sided row (H1): supported or inconclusive."""
    return "supported" if p < alpha else "inconclusive"


def h1b_category(p_adj: dict[str, float], alpha: float = 0.05) -> str:
    """Pre-registration 5.1 for H1b: supported on both datasets, partial on one."""
    n_sig = sum(p < alpha for p in p_adj.values())
    if n_sig == len(p_adj):
        return "supported"
    return "partial" if n_sig else "inconclusive"
