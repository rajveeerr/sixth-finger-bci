import mne
import numpy as np
import pandas as pd
import pytest
from mne.decoding import CSP
from sklearn.base import clone
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.metrics import balanced_accuracy_score
from sklearn.pipeline import make_pipeline

from sixthfinger.evaluation.leakage import LeakageError, assert_no_leakage
from sixthfinger.evaluation.splits import chrono_split, cv_leakfree_splits
from tests.evalfixtures import cohort_md, session_md, split_group


@pytest.fixture
def md():
    return session_md()


@pytest.fixture
def chrono(md):
    tr, te = chrono_split(md, ["01", "02"], ["03", "04"])
    return md.iloc[tr], md.iloc[te]


def test_correct_split_passes(md, chrono):
    train, test = chrono
    src = cohort_md(("sub-03", "sub-07"))
    assert_no_leakage(
        train,
        test,
        source=src,
        unlabelled=train[train.label == 0],
        target_subject="sub-01",
        split_group=split_group,
    )


def test_shared_trial_raises(chrono):
    train, test = chrono
    with pytest.raises(LeakageError, match="test trials in training"):
        assert_no_leakage(pd.concat([train, test.iloc[[1]]]), test)


def test_rest_window_of_a_test_trial_raises(md, chrono):
    train, test = chrono
    mi = test[test.label > 0].iloc[0]
    rest = md[(md.trial_uid == mi.trial_uid) & (md.label == 0)]
    with pytest.raises(LeakageError):
        assert_no_leakage(pd.concat([train, rest]), test.drop(rest.index))


def test_test_trial_in_unlabelled_raises(chrono):
    train, test = chrono
    with pytest.raises(LeakageError, match="unlabelled"):
        assert_no_leakage(train, test, unlabelled=test[test.label == 0])


def test_target_in_source_raises(chrono):
    train, test = chrono
    src = pd.concat([cohort_md(("sub-03",)), session_md("sub-01", "post")])
    with pytest.raises(LeakageError, match="sub-01"):
        assert_no_leakage(train, test, source=src, target_subject="sub-01")


def test_linked_partner_in_source_raises():
    md = session_md("sub-22")
    tr, te = chrono_split(md, ["01", "02"], ["03", "04"])
    src = cohort_md(("sub-01", "sub-21"))
    with pytest.raises(LeakageError, match="sub-21"):
        assert_no_leakage(
            md.iloc[tr], md.iloc[te], source=src, target_subject="sub-22", split_group=split_group
        )


def test_test_trial_in_source_raises(chrono):
    train, test = chrono
    with pytest.raises(LeakageError, match="source"):
        assert_no_leakage(train, test, source=test.iloc[:2])


def _shuffled_cv_score(replica: bool) -> float:
    """Mean CV balanced accuracy of CSP+LDA on shuffled labels (P01 step 4.4 in miniature)."""
    mne.set_log_level("ERROR")
    md = session_md(runs=(1, 2), drop_mi=())
    md = md[md.label > 0].reset_index(drop=True)
    rng = np.random.default_rng(0)
    # Many noise channels and few trials: room for a CSP fitted on everything to overfit.
    X = rng.standard_normal((len(md), 32, 100))
    X[md.label.to_numpy() == 2, 0] *= 3.0
    y = rng.permutation(md.label.to_numpy())
    md = md.assign(label=y)
    pipe = make_pipeline(CSP(n_components=6, log=True), LinearDiscriminantAnalysis())
    F = pipe[:-1].fit_transform(X, y) if replica else None
    scores = []
    for tr, te in cv_leakfree_splits(md, 10, 2, 0):
        if replica:
            pred = clone(pipe[-1]).fit(F[tr], y[tr]).predict(F[te])
        else:
            pred = clone(pipe).fit(X[tr], y[tr]).predict(X[te])
        scores.append(balanced_accuracy_score(y[te], pred))
    return float(np.mean(scores))


def test_label_permutation_exposes_the_replica_leak():
    assert _shuffled_cv_score(replica=False) <= 0.65
    assert _shuffled_cv_score(replica=True) >= 0.80
