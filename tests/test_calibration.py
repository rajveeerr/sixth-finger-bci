import numpy as np
import pytest

from sixthfinger.evaluation.calibration import complete_trials, draw_calibration_set, mi_trials
from tests.evalfixtures import session_md

AH, SF = 1, 2
S1 = dict(full_ids=[], budget_ids=[AH, SF], k_all=20)
S2 = dict(full_ids=[AH], budget_ids=[SF], k_all=20)


@pytest.fixture
def pool():
    md = session_md()
    return md[md.run.isin([1, 2])].reset_index(drop=True)


def _mi_counts(pool, idx):
    rows = pool.iloc[idx]
    return rows.label.value_counts().to_dict()


def test_s1_k5_draws_five_trials_per_class_with_their_rest(pool):
    cd = draw_calibration_set(pool, **S1, k=5, seed=0)
    assert _mi_counts(pool, cd.labelled_idx) == {0: 10, AH: 5, SF: 5}
    rows = pool.iloc[cd.labelled_idx]
    assert rows.trial_uid.nunique() == 10
    assert cd.k_used == {"1": 5, "2": 5}


def test_one_draw_serves_both_tasks(pool):
    cd = draw_calibration_set(pool, **S1, k=3, seed=4)
    t2 = pool.iloc[cd.labelled_idx]
    sf_trials = set(t2.trial_uid[t2.label == SF])
    t3 = t2[t2.trial_uid.isin(sf_trials) & t2.label.isin([0, SF])]
    assert len(t3) == 6 and set(t3.trial_uid) == sf_trials


def test_s2_k2_takes_every_ah_trial_and_two_sf(pool):
    cd = draw_calibration_set(pool, **S2, k=2, seed=0)
    n_ah = len(mi_trials(pool, AH))
    assert _mi_counts(pool, cd.labelled_idx) == {0: n_ah + 2, AH: n_ah, SF: 2}
    assert cd.k_used == {"2": 2}


def test_k_above_available_is_capped(pool):
    cd = draw_calibration_set(pool, **{**S1, "k_all": 30}, k=20, seed=0)
    assert cd.k_used == {"1": 20, "2": 19}
    assert _mi_counts(pool, cd.labelled_idx)[SF] == 19


def test_k_all_takes_every_trial_even_beyond_the_grid_value():
    # Pre-registration 3.4: "all" is every available trial; some pools have 21 or 22.
    md = session_md(runs=(1, 2, 3), drop_mi=(), drop_rest=((3, 1),))
    pool = md[md.run.isin([1, 2, 3])].reset_index(drop=True)  # 30 trials per class
    cd = draw_calibration_set(pool, **S1, k=20, seed=0)
    assert cd.k_used == {"1": 30, "2": 30}
    assert pool.iloc[cd.labelled_idx].trial_uid.nunique() == 60  # the incomplete one too


@pytest.mark.parametrize("seed", [0, 1, 2, "chrono"])
def test_draws_below_all_pick_only_trials_with_both_windows(seed):
    no_rest = (*((1, t) for t in range(1, 21, 2)), (2, 2), (2, 4))  # run 1 AH, two SF
    md = session_md(runs=(1, 2), drop_mi=((2, 6),), drop_rest=no_rest)
    pool = md.reset_index(drop=True)
    ok = complete_trials(pool)
    assert len(ok) == 40 - len(no_rest) - 1
    for k in (1, 3, 5, 10):
        rows = pool.iloc[draw_calibration_set(pool, **S1, k=k, seed=seed).labelled_idx]
        assert set(rows.trial_uid) <= ok
        for cid in (AH, SF):  # every drawn imagery trial brings its REST window
            uids = set(rows.trial_uid[rows.label == cid])
            assert uids <= set(rows.trial_uid[rows.label == 0])


@pytest.mark.parametrize("scen", [S1, S2])
def test_unlabelled_equals_labelled_for_k_above_zero(pool, scen):
    cd = draw_calibration_set(pool, **scen, k=3, seed=1)
    assert np.array_equal(cd.unlabelled_idx, cd.labelled_idx)


@pytest.mark.parametrize("scen", [S1, S2])
def test_k0_unlabelled_is_the_pool_rest(pool, scen):
    cd = draw_calibration_set(pool, **scen, k=0, seed=0)
    rows = pool.iloc[cd.unlabelled_idx]
    assert (rows.label == 0).all()
    assert len(rows) == (pool.label == 0).sum() == 40
    assert set(rows.run) == {1, 2}


def test_k0_labelled_is_empty_in_s1_and_ah_only_in_s2(pool):
    assert draw_calibration_set(pool, **S1, k=0, seed=0).labelled_idx.size == 0
    cd = draw_calibration_set(pool, **S2, k=0, seed=0)
    assert set(_mi_counts(pool, cd.labelled_idx)) == {0, AH}


def test_draws_are_reproducible_and_seed_dependent(pool):
    a = draw_calibration_set(pool, **S1, k=5, seed=3).labelled_idx
    b = draw_calibration_set(pool, **S1, k=5, seed=3).labelled_idx
    c = draw_calibration_set(pool, **S1, k=5, seed=4).labelled_idx
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_chrono_takes_the_first_trials_in_time_order(pool):
    cd = draw_calibration_set(pool, **S1, k=2, seed="chrono")
    rows = pool.iloc[cd.labelled_idx]
    for cid in (AH, SF):
        first = mi_trials(pool, cid).trial_uid.iloc[:2]
        assert set(rows.trial_uid[rows.label == cid]) == set(first)


def test_nothing_comes_from_test_runs():
    md = session_md()
    pool = md[md.run.isin([1, 2])].reset_index(drop=True)
    for k in (0, 1, 5, 20):
        cd = draw_calibration_set(pool, **S2, k=k, seed=0)
        rows = pool.iloc[np.concatenate([cd.labelled_idx, cd.unlabelled_idx])]
        assert set(rows.run) <= {1, 2}
