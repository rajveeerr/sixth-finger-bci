import importlib.util

import numpy as np
import pandas as pd
import pytest

from sixthfinger.paths import get_paths


@pytest.fixture(scope="module")
def lon():
    path = get_paths().root / "scripts" / "rq4_longitudinal.py"
    spec = importlib.util.spec_from_file_location("rq4_longitudinal", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _session(rng, mix, n=60, ch=6, t=200):
    """Three classes, each raising the variance of its own channel, seen through `mix`."""
    y = np.repeat([0, 1, 2], n // 3)
    X = rng.standard_normal((n, ch, t))
    for c in (1, 2):
        X[y == c, c] *= 3.0
    return np.einsum("cd,ndt->nct", mix, X), y


def test_recentring_undoes_a_change_of_channel_gains_between_sessions(lon):
    # Electrodes with another contact quality later: each channel scaled by its own gain.
    # Re-centring removes such a change (a general mixing would leave a rotation behind).
    rng = np.random.default_rng(0)
    eye = np.eye(6)
    shift = np.diag([0.3, 3.0, 0.5, 2.0, 1.0, 0.4])
    Xa, ya = _session(rng, eye)
    Xb, yb = _session(rng, shift)
    X = np.concatenate([Xa, Xb])
    md = pd.DataFrame({"label": np.r_[ya, yb]})
    pre, later = md.iloc[: len(ya)], md.iloc[len(ya) :]
    params = dict(covariance="oas", tangent_space_metric="riemann",
                  logreg={"C": 1.0, "max_iter": 1000}, target_weight=1)  # fmt: skip
    none = later.iloc[:0]
    model = lon.Recentred(params).fit(X, pre, none, unlabelled=later, test=none)
    acc_recentred = (model.predict_proba(Xb).argmax(1) == yb).mean()
    unchanged = lon.Recentred(params).fit(X, pre, none, unlabelled=pre, test=none)
    acc_unchanged = (unchanged.predict_proba(Xb).argmax(1) == yb).mean()
    assert acc_recentred > 0.8 and acc_recentred > acc_unchanged + 0.1


def test_no_fit_reads_a_test_window(lon):
    md = pd.DataFrame({"label": [0, 1, 2] * 4})
    test = md.iloc[9:]
    with pytest.raises(AssertionError, match="test window"):
        lon.Recentred({}).fit(None, md.iloc[:6], md.iloc[:0], unlabelled=md.iloc[6:], test=test)
    with pytest.raises(AssertionError, match="test window"):
        lon.fit_ts_lr(None, md, test)


def test_subject_rows_never_fit_on_the_later_sessions_test_runs(lon, monkeypatch):
    from sixthfinger.config import load_protocol_config
    from tests.evalfixtures import session_md

    md = pd.concat([session_md("sub-01", "pre"), session_md("sub-01", "post")], ignore_index=True)
    md = md.assign(group="B")
    rng = np.random.default_rng(0)
    X = rng.standard_normal((len(md), 6, 100)) * (1 + md.label.to_numpy()[:, None, None])
    test_index = set(md[(md.session == "post") & md.run.isin([3, 4])].index)
    fitted = []
    monkeypatch.setattr(lon, "outside", lambda test, *rows: fitted.extend(rows))
    monkeypatch.setattr(lon, "K_GRID", [0, 5])
    params = dict(covariance="oas", tangent_space_metric="riemann",
                  logreg={"C": 1.0, "max_iter": 200}, target_weight=1)  # fmt: skip
    rows = lon.subject_rows("sub-01", "post", X, md, load_protocol_config(), params)
    assert {r["arm"] for r in rows} == set(lon.ARMS)
    assert fitted and all(not set(f.index) & test_index for f in fitted)
