"""Group statistics: Wilcoxon, Holm, bootstrap, Friedman, learning-curve summaries."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import friedmanchisquare, wilcoxon
from statsmodels.stats.multitest import multipletests

# Defaults equal configs/protocol.yaml (stats); a test keeps the two together.
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 12345


def bootstrap_ci(
    values: np.ndarray,
    n: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
    level: float = 0.95,
) -> tuple[float, float, float]:
    """Mean and percentile bootstrap CI, resampling the values (subjects) with replacement."""
    rng = np.random.default_rng(seed)
    v = np.asarray(values, float)
    means = rng.choice(v, size=(n, v.size), replace=True).mean(axis=1)
    lo, hi = np.percentile(means, [(1 - level) / 2 * 100, (1 + level) / 2 * 100])
    return float(v.mean()), float(lo), float(hi)


def rank_biserial(d: np.ndarray) -> float:
    """Matched-pairs rank-biserial correlation, zero differences dropped as in the test."""
    nz = d[d != 0]
    if not nz.size:
        return 0.0
    ranks = pd.Series(np.abs(nz)).rank().to_numpy()
    return float((ranks[nz > 0].sum() - ranks[nz < 0].sum()) / ranks.sum())


def paired_test(a: np.ndarray, b: np.ndarray, alternative: str = "two-sided") -> dict:
    """Wilcoxon signed-rank on per-subject values a - b, with the effect sizes we report.

    alternative="greater" is the one-sided test a > b (H1, H1b, H2b, H3c).
    """
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = a - b
    if np.any(d != 0):
        res = wilcoxon(a, b, zero_method="wilcox", alternative=alternative, method="auto")
        w, p = float(res.statistic), float(res.pvalue)
    else:
        # scipy refuses an all-zero vector; there is simply no evidence either way.
        w, p = np.nan, 1.0
    mean, lo, hi = bootstrap_ci(d)
    return {
        "n": int(d.size),
        "n_nonzero": int(np.count_nonzero(d)),
        "median_diff": float(np.median(d)),
        "mean_diff": mean,
        "ci_lo": lo,
        "ci_hi": hi,
        "W": w,
        "p": p,
        "r_rb": rank_biserial(d),
        "alternative": alternative,
    }


def holm(pvals: list[float], alpha: float = 0.05) -> tuple[np.ndarray, np.ndarray]:
    reject, p_adj, _, _ = multipletests(pvals, alpha=alpha, method="holm")
    return reject, p_adj


def alc(k: np.ndarray, score_: np.ndarray, chance: float) -> float:
    """Area under the learning curve on a ln(1 + k) axis, 0 at chance and 1 at perfect.

    k are nominal budgets, all >= 1 (protocol 6); score_ is balanced accuracy at each k.
    """
    k = np.asarray(k, float)
    if k.size < 2 or k.min() < 1:
        raise ValueError(f"ALC needs at least two budgets, all >= 1; got {k.tolist()}")
    x = np.log1p(k)
    y = (np.asarray(score_, float) - chance) / (1 - chance)
    order = np.argsort(x)
    return float(np.trapezoid(y[order], x[order]) / (x.max() - x.min()))


def paired_alc(
    k: np.ndarray, a: np.ndarray, b: np.ndarray, chance: float
) -> tuple[float, float, list[int]]:
    """ALC of two methods over the budgets where both are defined (not NaN)."""
    k, a, b = (np.asarray(v, float) for v in (k, a, b))
    ok = ~(np.isnan(a) | np.isnan(b))
    return alc(k[ok], a[ok], chance), alc(k[ok], b[ok], chance), k[ok].astype(int).tolist()


def subject_curve(scores: pd.DataFrame, value: str = "bal_acc") -> pd.DataFrame:
    """Per-subject value at each k: mean over the random draws, chrono draw left out."""
    random_draws = scores[scores.draw.astype(str) != "chrono"]
    keys = ["method", "subject", "k"]
    return random_draws.groupby(keys, as_index=False)[value].mean()


def k_star(k: np.ndarray, score_: np.ndarray, threshold: float) -> float:
    """Smallest k whose score reaches the threshold; inf if never."""
    hit = np.asarray(k)[np.asarray(score_) >= threshold]
    return float(hit.min()) if hit.size else float("inf")


def friedman(table: pd.DataFrame) -> dict:
    """table: rows = subjects, columns = methods."""
    stat, p = friedmanchisquare(*[table[c].to_numpy() for c in table.columns])
    mean_ranks = table.rank(axis=1, ascending=False).mean().to_dict()
    return {"chi2": float(stat), "p": float(p), "mean_ranks": mean_ranks}
