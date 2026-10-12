import numpy as np
import pytest

from sixthfinger.viz import explain


def test_channel_covariance_matches_numpy_in_batches():
    X = np.random.default_rng(0).standard_normal((37, 5, 20))
    expected = np.cov(X.transpose(1, 0, 2).reshape(5, -1))
    np.testing.assert_allclose(explain.channel_covariance(X, batch=8), expected, atol=1e-10)


def test_haufe_patterns_recover_the_source_not_the_filter():
    # The signal is on channel 0; a noise source reaches channels 0 and 1. The filter that
    # extracts the signal subtracts channel 1 from channel 0, but the pattern is channel 0.
    rng = np.random.default_rng(1)
    a, b = np.array([1.0, 0, 0, 0]), np.array([1.0, 1, 0, 0])
    X = np.outer(a, rng.standard_normal(20000)) + np.outer(b, rng.standard_normal(20000))
    X += 0.01 * rng.standard_normal(X.shape)
    w = np.array([[1.0, -1, 0, 0]])
    pattern = explain.haufe_patterns(w, np.cov(X))[0]
    assert np.corrcoef(pattern, a)[0, 1] > 0.999
    assert np.corrcoef(w[0], a)[0, 1] < 0.9


def test_shares_and_normalisation():
    channels = ["AF3", "AF4", "F5", "F6", "C3", "POz", "PO3", "PO4", "PO5", "PO6"]
    m = explain.normalised_abs(np.array([[-2.0, 1, 1, 0, 4, 0, 0, 0, 0, 0]]))[0]
    assert m.max() == 1 and (m >= 0).all()
    assert explain.weight_share(m, channels, explain.FRONTAL) == pytest.approx(4 / 8)
    assert explain.weight_share(m, channels, explain.PARIETO_OCCIPITAL) == 0
