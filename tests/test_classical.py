import numpy as np
import pandas as pd
import pytest

from sixthfinger.config import load_data_config
from sixthfinger.evaluation.runner import method_params
from sixthfinger.models.registry import REGISTRY, Batch, make_method
from sixthfinger.paths import get_paths
from sixthfinger.preprocessing.filters import BandPass, bandpass, ersp_db

RQ1_METHODS = ["csp_lda", "csp_lda_replica", "csp_svm", "fbcsp_lda", "mdm", "ts_lr"]
SFREQ = 250.0


def _params(name: str) -> dict:
    return method_params(name, get_paths().configs)


def _planted(n_per_class=30, n_classes=2, n_channels=8, n_times=500, seed=0):
    """Gaussian noise with a 10 Hz rhythm that is stronger on one channel per class."""
    rng = np.random.default_rng(seed)
    t = np.arange(n_times) / SFREQ
    X, y = [], []
    for label in range(1, n_classes + 1):
        for _ in range(n_per_class):
            x = rng.standard_normal((n_channels, n_times))
            x[label] += 3 * np.sin(2 * np.pi * 10 * t + rng.uniform(0, 2 * np.pi))
            X.append(x)
            y.append(label)
    X = np.asarray(X, np.float32) * 1e-6
    md = pd.DataFrame({"trial_uid": [f"t{i}" for i in range(len(y))], "label": y})
    return X, np.asarray(y), md


def _split(y, seed=1):
    idx = np.random.default_rng(seed).permutation(len(y))
    cut = len(y) * 2 // 3
    return idx[:cut], idx[cut:]


def test_every_rq1_method_is_registered_with_a_config():
    for name in RQ1_METHODS:
        assert name in REGISTRY
        assert _params(name), f"configs/models/{name}.yaml missing or empty"


def test_configs_hold_the_preregistered_hyperparameters():
    # Pre-registration 3.6; any change here is a deviation and must be logged.
    assert _params("csp_lda") == {
        "csp": {"n_components": 6, "reg": "ledoit_wolf", "log": True},
        "lda": {"solver": "lsqr", "shrinkage": "auto"},
    }
    replica = _params("csp_lda_replica")
    assert replica["csp"] == {"n_components": 10, "reg": None, "log": True}
    assert replica["lda"] == {}
    assert replica["ersp_mu"] == {"band_hz": [8.0, 13.0], "baseline_s": [-1.0, 0.0]}
    assert _params("csp_svm")["csp"] == _params("csp_lda")["csp"]
    assert _params("csp_svm")["svm"] == {
        "kernel": "linear",
        "C": 1.0,
        "probability": True,
        "random_state": 0,
    }
    fb = _params("fbcsp_lda")
    assert fb["bands"] == [[8, 12], [12, 16], [16, 20], [20, 24], [24, 28], [28, 32]]
    assert fb["csp"] == {"n_components": 4, "reg": "ledoit_wolf", "log": True}
    assert (fb["select_k"], fb["filter_order"]) == (8, 4)
    assert fb["lda"] == _params("csp_lda")["lda"]
    assert fb["sfreq"] == load_data_config().signal.sfreq
    assert _params("mdm") == {"covariance": "oas", "metric": "riemann"}
    assert _params("ts_lr") == {
        "covariance": "oas",
        "tangent_space_metric": "riemann",
        "logreg": {"C": 1.0, "max_iter": 1000},
    }


@pytest.mark.parametrize("name", ["csp_lda", "csp_svm", "fbcsp_lda", "mdm", "ts_lr"])
@pytest.mark.parametrize("n_classes", [2, 3])
def test_methods_learn_a_planted_rhythm(name, n_classes):
    X, y, md = _planted(n_classes=n_classes)
    tr, te = _split(y)
    method = make_method(name, n_classes=n_classes, **_params(name))
    method.fit(Batch(X[tr], y[tr], md.iloc[tr]))
    proba = method.predict_proba(X[te])
    assert proba.shape == (len(te), n_classes)
    assert np.allclose(proba.sum(axis=1), 1)
    pred = np.sort(np.unique(y))[proba.argmax(axis=1)]
    assert (pred == y[te]).mean() > 0.8


def test_replica_method_runs_on_ersp_shaped_input():
    X, y, md = _planted(n_channels=12)
    tr, te = _split(y)
    method = make_method("csp_lda_replica", n_classes=2, **_params("csp_lda_replica"))
    assert method.feature == "ersp_mu"
    method.fit(Batch(X[tr], y[tr], md.iloc[tr]))
    assert method.predict_proba(X[te]).shape == (len(te), 2)


def test_declared_minimum_trials():
    # CSP needs a covariance per class (protocol 4.2); MDM and TS+LR work from one trial.
    for name in ("csp_lda", "csp_lda_replica", "csp_svm", "fbcsp_lda"):
        assert REGISTRY[name].min_trials_per_class == 2
    X, y, md = _planted(n_per_class=1)
    for name in ("mdm", "ts_lr"):
        assert getattr(REGISTRY[name], "min_trials_per_class", 1) == 1
        method = make_method(name, n_classes=2, **_params(name)).fit(Batch(X, y, md))
        assert method.predict_proba(X).shape == (2, 2)


@pytest.mark.parametrize("name", ["csp_svm", "fbcsp_lda"])
def test_randomised_steps_are_seeded(name):
    X, y, md = _planted()
    tr, te = _split(y)
    runs = [
        make_method(name, n_classes=2, **_params(name))
        .fit(Batch(X[tr], y[tr], md.iloc[tr]))
        .predict_proba(X[te])
        for _ in range(2)
    ]
    assert np.array_equal(runs[0], runs[1])


def test_paper_replica_split_point_is_before_the_classifier():
    # The replica fits pipe[:-1] on all windows; for these methods that is everything but
    # the classifier, so the leak is in CSP, selection or the tangent-space reference only.
    last = {
        "csp_lda": "lineardiscriminantanalysis",
        "csp_svm": "svc",
        "fbcsp_lda": "lineardiscriminantanalysis",
        "mdm": "mdm",
        "ts_lr": "logisticregression",
    }
    for name, step in last.items():
        pipe = make_method(name, n_classes=2, **_params(name)).build()
        assert pipe.steps[-1][0] == step


def test_bandpass_keeps_the_band_and_removes_the_rest():
    t = np.arange(2000) / SFREQ
    inside, outside = np.sin(2 * np.pi * 10 * t), np.sin(2 * np.pi * 40 * t)
    out = bandpass(np.stack([inside, outside])[None], 8, 12, SFREQ)
    mid = slice(500, 1500)  # away from the filter's edge transients
    assert out.dtype == np.float32
    assert np.std(out[0, 0, mid]) == pytest.approx(np.std(inside[mid]), rel=0.05)
    assert np.std(out[0, 1, mid]) < 0.01
    step = BandPass(8, 12, SFREQ)
    assert step.fit(None) is step
    assert np.array_equal(step.transform(np.stack([inside])[None]), out[:, :1])


def test_ersp_is_db_change_from_each_windows_own_baseline():
    # 1 s baseline, 1 s gap, 4 s kept; the 10 Hz amplitude halves after the baseline.
    t = np.arange(1500) / SFREQ
    amp = np.where(t < 1.0, 1.0, 0.5)
    x = (amp * np.sin(2 * np.pi * 10 * t))[None, None]
    scaled = np.concatenate([x, 7.0 * x])  # a louder copy must give the same dB
    out = ersp_db(scaled, SFREQ, (8.0, 13.0), baseline=(0, 250), keep=(500, 1500))
    assert out.shape == (2, 1, 1000) and out.dtype == np.float32
    mid = out[:, 0, 200:800]
    assert np.allclose(mid.mean(axis=-1), 20 * np.log10(0.5), atol=0.3)
    assert np.allclose(out[0], out[1], atol=1e-4)


def test_filter_bank_layout_matches_one_filter_per_band():
    from functools import partial

    from sklearn.feature_selection import SelectKBest, mutual_info_classif
    from sklearn.pipeline import make_pipeline, make_union

    from sixthfinger.models.classical import _csp, _lda

    p = _params("fbcsp_lda")
    X, y, md = _planted(n_channels=10)
    tr, te = _split(y)
    # The textbook layout: a band-pass and a CSP per band side by side.
    score = partial(mutual_info_classif, random_state=p["mutual_info_random_state"])
    union = make_pipeline(
        make_union(
            *[
                make_pipeline(BandPass(lo, hi, p["sfreq"], p["filter_order"]), _csp(p["csp"]))
                for lo, hi in p["bands"]
            ]
        ),
        SelectKBest(score, k=p["select_k"]),
        _lda(p["lda"]),
    ).fit(X[tr], y[tr])
    ours = make_method("fbcsp_lda", n_classes=2, **p).fit(Batch(X[tr], y[tr], md.iloc[tr]))
    assert np.array_equal(ours.predict_proba(X[te]), union.predict_proba(X[te]))


def test_filter_bank_once_per_session_gives_the_same_folds():
    from sixthfinger.evaluation.runner import score_folds

    X, y, md = _planted(n_channels=10)
    splits = [(0, _split(y, seed=1)), (1, _split(y, seed=2))]
    p = _params("fbcsp_lda")
    rows = list(score_folds(X, y, md, splits, "fbcsp_lda", p, [1, 2], "cv_leakfree", 0))
    for (fold, (tr, te)), (_, metrics, _) in zip(splits, rows, strict=True):
        method = make_method("fbcsp_lda", n_classes=2, **p).fit(Batch(X[tr], y[tr], md.iloc[tr]))
        pred = np.array([1, 2])[method.predict_proba(X[te]).argmax(axis=1)]
        assert metrics["acc"] == (pred == y[te]).mean(), fold


def _csp_that_fails(monkeypatch):
    # The real failure is borderline: MNE judges the summed covariance full rank and then its
    # Cholesky factor breaks (sub-18 post, run 02 held out). Synthetic data cannot sit on that
    # edge reliably, so the factorisation error is raised directly.
    from mne.decoding import CSP
    from scipy.linalg import LinAlgError

    def fail(self, X, y):
        raise LinAlgError("The leading minor of order 40 of B is not positive definite.")

    monkeypatch.setattr(CSP, "fit", fail)


def test_unregularised_csp_declares_a_failed_factorisation_undefined(monkeypatch):
    from sixthfinger.models.classical import _csp
    from sixthfinger.models.registry import UndefinedCell

    X, y, _ = _planted()
    _csp_that_fails(monkeypatch)
    with pytest.raises(UndefinedCell, match="unregularised CSP undefined"):
        _csp({"n_components": 4, "reg": None, "log": True}).fit(X, y)
    # With shrinkage nothing is declared: a failure there would be a bug and must surface.
    with pytest.raises(Exception, match="leading minor") as err:
        _csp({"n_components": 4, "reg": "ledoit_wolf", "log": True}).fit(X, y)
    assert not isinstance(err.value, UndefinedCell)


@pytest.mark.parametrize("protocol", ["cv_leakfree", "paper_replica"])
def test_runner_writes_an_undefined_fold_as_missing_with_its_reason(monkeypatch, protocol):
    from sixthfinger.evaluation.runner import score_folds

    X, y, md = _planted()
    tr, te = _split(y)
    _csp_that_fails(monkeypatch)
    params = {"csp": {"n_components": 4, "reg": None, "log": True}, "lda": {}}
    rows = list(score_folds(X, y, md, [(0, (tr, te))], "csp_lda", params, [1, 2], protocol, 0))
    assert len(rows) == 1
    fold, metrics, extra = rows[0]
    assert fold == 0 and metrics is None
    assert extra["reason"].startswith("unregularised CSP undefined")


@pytest.mark.real_data
def test_replica_is_undefined_on_three_sub18_post_folds():
    # Found by replaying every honest CSP fold of the unfinished sessions on 2026-10-10: only
    # these three cv_leakfree folds fail, all of them for the unregularised replica.
    from sixthfinger.config import load_protocol_config
    from sixthfinger.data.epochs import load_windows
    from sixthfinger.evaluation.runner import ersp_input, within_splits
    from sixthfinger.models.registry import UndefinedCell

    paths, cfg = get_paths(), load_data_config()
    params = _params("csp_lda_replica")
    _, md = load_windows(paths.epochs, cfg, subjects=["sub-18"], sessions=["post"], labels=[1, 2])
    md, X = ersp_input(md.reset_index(drop=True), cfg, paths.processed, params["ersp_mu"])
    y = md.label.to_numpy()
    splits, _ = within_splits("cv_leakfree", md, load_protocol_config())
    for fold in (5, 14, 55):
        tr, _te = splits[fold]
        method = make_method("csp_lda_replica", n_classes=2, **params)
        with pytest.raises(UndefinedCell):
            method.fit(Batch(X[tr], y[tr], md.iloc[tr]))
    tr, _te = splits[0]
    make_method("csp_lda_replica", n_classes=2, **params).fit(Batch(X[tr], y[tr], md.iloc[tr]))
