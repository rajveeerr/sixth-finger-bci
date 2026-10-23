import importlib.util

import numpy as np
import pandas as pd
import pytest

from sixthfinger.config import load_data_config
from sixthfinger.paths import get_paths


@pytest.fixture(scope="module")
def rq1():
    path = get_paths().root / "scripts" / "summarise_rq1.py"
    spec = importlib.util.spec_from_file_location("summarise_rq1", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def values():
    """Per-subject values shaped like rq1_subject_values.csv, replica 10 points up."""
    cfg = load_data_config()
    rng = np.random.default_rng(0)
    rows = []
    for subject in cfg.subjects.ids:
        for session in cfg.sessions_for(subject):
            base = rng.uniform(0.45, 0.65)
            for method, feature in (("csp_lda", "bandpower"), ("csp_lda_replica", "ersp_mu")):
                for protocol, shift in (
                    ("paper_replica", 0.10),
                    ("cv_leakfree", 0.0),
                    ("loro", -0.01),
                    ("chrono", -0.02),
                ):
                    bal = base + shift + rng.normal(0, 0.01)
                    rows.append(
                        dict(
                            experiment="rq1_benchmark",
                            task="T1_ah_vs_sf",
                            method=method,
                            feature=feature,
                            protocol=protocol,
                            subject=subject,
                            session=session,
                            bal_acc=bal,
                            acc=bal,
                            above_chance=bal > 0.59,
                        )
                    )
    return pd.DataFrame(rows)


def test_h1_rows_use_the_preregistered_populations(rq1, values):
    stats = rq1.stats_table(values, load_data_config(), ["sub-01", "sub-03"]).set_index("test_id")
    assert stats.loc["H1", "n"] == 22 and stats.loc["H1", "role"] == "confirmatory"
    assert stats.loc["H1_without_dev", "n"] == 20
    assert stats.loc["H1_post_all", "n"] == 24
    assert stats.loc["H1_post_linked_merged", "n"] == 23
    assert stats.loc["H1_follow", "n"] == 18
    # Every subject gains about 10 points: one-sided p is tiny and the category is set.
    assert stats.loc["H1", "mean_diff"] == pytest.approx(10, abs=1)
    assert stats.loc["H1", "category"] == "supported"
    assert stats.loc["H1_post_all", "same_category_as_pre"]
    desc = stats.loc["descriptive"]
    assert len(desc) == 3 * 2 * 3  # comparisons x methods x sessions
    assert (desc.p_holm >= desc.p).all()


def test_group_table_counts_subjects_per_population(rq1, values):
    table = rq1.group_table(values, load_data_config(), ["sub-01", "sub-03"], {"T1_ah_vs_sf": 2})
    cv = table[(table.method == "csp_lda") & (table.protocol == "cv_leakfree")]
    n = cv.set_index(["session", "population"]).n
    assert n[("pre", "all")] == 22 and n[("pre", "without_dev")] == 20
    assert n[("post", "all")] == 24 and n[("post", "linked_merged")] == 23
    assert n[("follow", "all")] == 18
    pre = values[(values.method == "csp_lda") & (values.protocol == "cv_leakfree")]
    pre = pre[pre.session == "pre"]
    row = cv.set_index(["session", "population"]).loc[("pre", "all")]
    assert row.n_below_chance_level == (pre.bal_acc < 0.5).sum()
    assert row.min_bal_acc == pre.bal_acc.min() and row.max_bal_acc == pre.bal_acc.max()


def test_runwise_gap_matches_h1_and_describes_the_splits(rq1, values):
    gap = rq1.runwise_gap(values).set_index(["session", "comparison"])
    stats = rq1.stats_table(values, load_data_config(), ["sub-01", "sub-03"])
    h1 = stats[stats.test_id == "H1"].iloc[0]
    same = gap.loc[("pre", "paper_replica - cv_leakfree")]
    assert same["mean"] == pytest.approx(h1.mean_diff)
    assert same.ci_lo == pytest.approx(h1.ci_lo) and same.ci_hi == pytest.approx(h1.ci_hi)
    assert gap.loc[("pre", "paper_replica - chrono"), "mean"] > same["mean"]
