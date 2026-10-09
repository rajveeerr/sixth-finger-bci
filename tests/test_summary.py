import numpy as np
import pandas as pd
import pytest

from sixthfinger.evaluation.summary import (
    describe,
    h1b_category,
    holm_family,
    merge_linked,
    one_sided_category,
    paired,
    subject_values,
)
from tests.evalfixtures import split_group


def _folds(protocol, n_folds, repeats, bal, n_test=8, subject="sub-01"):
    n = n_folds * repeats
    return pd.DataFrame(
        {
            "protocol": protocol,
            "subject": subject,
            "fold": range(n),
            "n_folds": n_folds,
            "n_test": n_test,
            "bal_acc": bal,
            "acc": bal,
        }
    )


def test_subject_values_count_one_repeat_for_cv_and_every_fold_otherwise():
    scores = pd.concat(
        [
            _folds("cv_leakfree", 10, 10, np.linspace(0.4, 0.6, 100)),
            _folds("loro", 4, 1, [0.5, 0.6, 0.7, 0.8], n_test=20),
            _folds("chrono", 1, 1, [0.9], n_test=40),
        ]
    )
    out = subject_values(scores, ["protocol", "subject"], n_classes=2).set_index("protocol")
    assert out.loc["cv_leakfree", "n_windows"] == 80 and out.loc["cv_leakfree", "n_fits"] == 100
    assert out.loc["cv_leakfree", "bal_acc"] == pytest.approx(0.5)
    assert out.loc["loro", "n_windows"] == 80 and out.loc["loro", "bal_acc"] == pytest.approx(0.65)
    assert out.loc["chrono", "n_windows"] == 40
    # Binomial threshold for 80 windows and two classes is 0.5875 (P05 known answer).
    assert out.loc["loro", "chance_threshold"] == pytest.approx(0.5875)
    assert out.above_chance.tolist() == [True, False, True]


def test_describe_skips_missing_values():
    d = describe([0.5, 0.7, np.nan])
    assert d["n"] == 2 and d["mean"] == pytest.approx(0.6) and d["median"] == pytest.approx(0.6)
    assert d["ci_lo"] <= 0.6 <= d["ci_hi"]
    assert describe([])["n"] == 0


def test_linked_subjects_become_one_value():
    values = pd.DataFrame(
        {
            "protocol": "cv_leakfree",
            "subject": ["sub-01", "sub-21", "sub-22"],
            "bal_acc": [0.5, 0.6, 0.8],
            "acc": [0.5, 0.6, 0.8],
        }
    )
    merged = merge_linked(values, split_group).set_index("subject")
    assert len(merged) == 2 and merged.loc["sub-21+sub-22", "bal_acc"] == pytest.approx(0.7)


def test_paired_reports_points():
    wide = pd.DataFrame({"a": [0.6, 0.7, 0.8, 0.9, 0.65, 0.75], "b": [0.5] * 6})
    wide.loc[6] = [0.9, np.nan]  # a subject without the second value is left out
    res = paired(wide, "a", "b", alternative="greater")
    assert res["n"] == 6 and res["p"] == pytest.approx(0.015625)
    assert res["mean_diff"] == pytest.approx(100 * (wide.a[:6].mean() - 0.5))


def test_paired_without_any_defined_pair_is_empty_not_an_error():
    # Cho2017's chrono cells are all declared missing, so pivot_table drops the column.
    wide = pd.DataFrame({"loro": [0.6, 0.7, 0.8]}, index=["s1", "s2", "s3"])
    res = paired(wide, "loro", "chrono")
    assert res["n"] == 0 and np.isnan(res["p"]) and np.isnan(res["mean_diff"])


def test_holm_family_keeps_a_member_that_was_not_run():
    adj = holm_family({"BNCI2014_001": 0.004, "Cho2017": None})
    assert adj == {"BNCI2014_001": pytest.approx(0.008), "Cho2017": 1.0}
    assert holm_family({"a": 0.01, "b": 0.04}) == {"a": 0.02, "b": 0.04}


def test_outcome_categories_follow_the_preregistration():
    assert one_sided_category(0.049) == "supported"
    assert one_sided_category(0.05) == "inconclusive"
    assert h1b_category({"a": 0.01, "b": 0.02}) == "supported"
    assert h1b_category({"a": 0.01, "b": 1.0}) == "partial"
    assert h1b_category({"a": 0.2, "b": 1.0}) == "inconclusive"
