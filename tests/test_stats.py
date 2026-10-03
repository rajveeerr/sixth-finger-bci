import numpy as np
import pandas as pd
import pytest
from statsmodels.stats.multitest import multipletests

from sixthfinger.evaluation.stats import (
    alc,
    bootstrap_ci,
    friedman,
    holm,
    k_star,
    paired_alc,
    paired_test,
    subject_curve,
)


def test_six_positive_differences_give_the_exact_p():
    a = np.array([0.6, 0.7, 0.8, 0.9, 0.65, 0.75])
    b = a - np.array([0.01, 0.02, 0.03, 0.04, 0.05, 0.06])
    res = paired_test(a, b)
    assert res["p"] == pytest.approx(0.03125)
    assert res["r_rb"] == pytest.approx(1.0)
    assert res["n"] == 6 and res["W"] == 0.0


def test_one_sided_halves_the_p():
    a = np.array([0.6, 0.7, 0.8, 0.9, 0.65, 0.75])
    b = a - np.array([0.01, 0.02, 0.03, 0.04, 0.05, 0.06])
    assert paired_test(a, b, "greater")["p"] == pytest.approx(0.015625)
    assert paired_test(a, b, "less")["p"] > 0.9


def test_zero_differences_are_dropped_and_counted():
    a = np.array([0.5, 0.6, 0.7, 0.8, 0.9, 0.55, 0.65])
    b = a - np.array([0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06])
    res = paired_test(a, b)
    assert res["n"] == 7 and res["n_nonzero"] == 6
    assert res["p"] == pytest.approx(0.03125)


def test_identical_methods_give_no_evidence():
    a = np.full(5, 0.5)
    res = paired_test(a, a)
    assert res["p"] == 1.0 and res["r_rb"] == 0.0


def test_bootstrap_is_reproducible_and_brackets_the_mean():
    v = np.random.default_rng(0).normal(0.1, 0.05, 22)
    m, lo, hi = bootstrap_ci(v)
    assert (m, lo, hi) == bootstrap_ci(v)
    assert lo < m < hi and m == pytest.approx(v.mean())


def test_holm_matches_statsmodels():
    p = [0.01, 0.04, 0.03, 0.2]
    reject, p_adj = holm(p)
    ref = multipletests(p, method="holm")
    assert np.allclose(p_adj, ref[1]) and (reject == ref[0]).all()
    assert np.allclose(p_adj, [0.04, 0.09, 0.09, 0.2])


def test_alc_is_one_for_perfect_and_zero_for_chance():
    k = np.array([1, 2, 3, 5, 10])
    assert alc(k, np.ones(5), 1 / 3) == pytest.approx(1.0)
    assert alc(k, np.full(5, 1 / 3), 1 / 3) == pytest.approx(0.0)
    assert alc(k, np.full(5, 0.25), 0.5) == pytest.approx(-0.5)


def test_alc_uses_the_log_axis():
    k = np.array([1, 3])
    # Linear in ln(1 + k) between y = 0 and y = 1: the area is the mean, 0.5.
    assert alc(k, np.array([0.5, 1.0]), 0.5) == pytest.approx(0.5)
    assert alc(k[::-1], np.array([1.0, 0.5]), 0.5) == pytest.approx(0.5)


def test_alc_refuses_k_zero():
    with pytest.raises(ValueError):
        alc(np.array([0, 1, 2]), np.ones(3), 0.5)


def test_paired_alc_drops_undefined_budgets():
    k = np.array([1, 2, 3, 5])
    a = np.array([np.nan, 0.6, 0.7, 0.8])
    b = np.array([0.5, 0.55, 0.6, 0.65])
    _, alc_b, used = paired_alc(k, a, b, 0.5)
    assert used == [2, 3, 5]
    assert alc_b == pytest.approx(alc(k[1:], b[1:], 0.5))


def test_subject_curve_leaves_out_the_chrono_draw():
    scores = pd.DataFrame(
        {
            "method": "m",
            "subject": "sub-01",
            "k": [2, 2, 2],
            "draw": ["0", "1", "chrono"],
            "bal_acc": [0.4, 0.6, 1.0],
        }
    )
    assert subject_curve(scores).bal_acc.tolist() == [pytest.approx(0.5)]


def test_k_star():
    k = np.array([1, 2, 3, 5])
    assert k_star(k, np.array([0.5, 0.72, 0.6, 0.8]), 0.7) == 2
    assert k_star(k, np.array([0.5, 0.6, 0.6, 0.6]), 0.7) == float("inf")


def test_friedman_ranks_the_better_method_first():
    rng = np.random.default_rng(0)
    base = rng.uniform(0.4, 0.6, 12)
    table = pd.DataFrame({"a": base + 0.1, "b": base, "c": base - 0.05})
    res = friedman(table)
    assert res["p"] < 0.01
    assert res["mean_ranks"]["a"] == pytest.approx(1.0)


def test_bootstrap_defaults_are_the_protocol_values():
    from sixthfinger.config import load_protocol_config
    from sixthfinger.evaluation import stats

    cfg = load_protocol_config().stats
    assert cfg.bootstrap_resamples == stats.BOOTSTRAP_RESAMPLES
    assert cfg.bootstrap_seed == stats.BOOTSTRAP_SEED
