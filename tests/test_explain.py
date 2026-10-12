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


def test_each_eegnet_spatial_filter_uses_the_covariance_of_its_own_temporal_feature():
    import torch
    from braindecode.models import EEGNet

    torch.manual_seed(0)
    net = EEGNet(n_chans=2, n_outputs=2, n_times=256, F1=2, D=2, F2=4).eval()
    n = np.arange(256)
    with torch.no_grad():
        w = torch.zeros_like(net.conv_temporal.weight)  # (F1, 1, 1, 64)
        w[0, 0, 0, :] = 1.0 / 64  # feature 0: moving average, keeps the slow channel
        w[1, 0, 0, 31], w[1, 0, 0, 32] = 1.0, -1.0  # feature 1: difference, keeps the fast one
        net.conv_temporal.weight.copy_(w)
    rng = np.random.default_rng(0)
    X = np.zeros((40, 2, 256), np.float32)
    for i in range(40):
        X[i, 0] = 5 * np.sin(2 * np.pi * 2 * n / 250 + rng.uniform(0, 6))  # slow, channel 0
        X[i, 1] = 5 * np.sin(2 * np.pi * 60 * n / 250 + rng.uniform(0, 6))  # fast, channel 1
    with torch.no_grad():  # every spatial filter weighs both channels equally
        net.conv_spatial.parametrizations.weight.original.fill_(0.5)
    patterns = np.abs(explain.eegnet_patterns(net, X))
    # Filters 0 and 1 see feature 0 (the slow channel), filters 2 and 3 feature 1.
    assert patterns[:2].argmax(axis=1).tolist() == [0, 0]
    assert patterns[2:].argmax(axis=1).tolist() == [1, 1]
