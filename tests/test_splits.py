import numpy as np

from sixthfinger.evaluation.splits import (
    chrono_split,
    cv_leakfree_splits,
    loro_splits,
    loso_groups,
    n_cv_folds,
    paper_replica_splits,
)
from tests.evalfixtures import session_md, split_group


def _uids(md, idx):
    return set(md.trial_uid.iloc[idx])


def _all_splits(md):
    yield from cv_leakfree_splits(md, 10, 2, 0)
    yield from loro_splits(md)
    yield chrono_split(md, ["01", "02"], ["03", "04"])


def test_no_trial_on_both_sides():
    md = session_md()
    for tr, te in _all_splits(md):
        assert len(te) and not _uids(md, tr) & _uids(md, te)


def test_cv_folds_cover_every_window_once_per_repeat():
    md = session_md()
    tests = [te for _, te in cv_leakfree_splits(md, 10, 3, 0)]
    assert len(tests) == 30
    for rep in range(3):
        covered = np.sort(np.concatenate(tests[rep * 10 : (rep + 1) * 10]))
        assert np.array_equal(covered, np.arange(len(md)))


def test_cv_is_stratified_by_trial_class():
    md = session_md(drop_mi=())
    for _, te in cv_leakfree_splits(md, 10, 1, 0):
        mi = md.iloc[te].query("label > 0").label.value_counts()
        assert mi[1] == mi[2] == 4


def test_replica_uses_the_same_folds():
    md = session_md()
    a = list(cv_leakfree_splits(md, 10, 2, 0))
    b = list(paper_replica_splits(md, 10, 2, 0))
    assert all(np.array_equal(x[1], y[1]) for x, y in zip(a, b, strict=True))


def test_seed_changes_the_folds():
    md = session_md()
    a = next(cv_leakfree_splits(md, 10, 1, 0))[1]
    b = next(cv_leakfree_splits(md, 10, 1, 1))[1]
    assert not np.array_equal(a, b)


def test_n_cv_folds_caps_at_the_smallest_class():
    md = session_md(runs=(1,), drop_mi=((1, 2), (1, 4), (1, 6)))
    assert n_cv_folds(md, 10) == 7


def test_loro_one_fold_per_run():
    md = session_md()
    folds = list(loro_splits(md))
    assert len(folds) == 4
    for tr, te in folds:
        assert md.run.iloc[te].nunique() == 1
        assert md.run.iloc[te].iloc[0] not in set(md.run.iloc[tr])


def test_chrono_trains_on_runs_1_2_only():
    md = session_md()
    tr, te = chrono_split(md, ["01", "02"], ["03", "04"])
    assert set(md.run.iloc[tr]) == {1, 2}
    assert set(md.run.iloc[te]) == {3, 4}


def test_missing_run_is_tolerated():
    md = session_md(runs=(1, 3, 4))
    assert len(list(loro_splits(md))) == 3
    tr, te = chrono_split(md, ["01", "02"], ["03", "04"])
    assert set(md.run.iloc[tr]) == {1}
    assert set(md.run.iloc[te]) == {3, 4}


def test_loso_keeps_linked_subjects_apart():
    subjects = ["sub-01", "sub-03", "sub-21", "sub-22"]
    groups = loso_groups(subjects, split_group)
    assert "sub-21" not in groups["sub-22"] and "sub-22" not in groups["sub-21"]
    assert groups["sub-01"] == ["sub-03", "sub-21", "sub-22"]
    assert all(t not in src for t, src in groups.items())
