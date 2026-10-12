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
    model = lon.Recentred(params).fit(X, pre, later.iloc[:0], unlabelled=later)
    acc_recentred = (model.predict_proba(Xb).argmax(1) == yb).mean()
    unchanged = lon.Recentred(params).fit(X, pre, later.iloc[:0], unlabelled=pre)
    acc_unchanged = (unchanged.predict_proba(Xb).argmax(1) == yb).mean()
    assert acc_recentred > 0.8 and acc_recentred > acc_unchanged + 0.1
