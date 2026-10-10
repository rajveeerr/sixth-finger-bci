import numpy as np
import pytest

from sixthfinger.preprocessing.alignment import align, align_by_subject, reference_matrix


def _windows(n=60, ch=8, t=200, seed=0, mix=None):
    rng = np.random.default_rng(seed)
    A = mix if mix is not None else rng.standard_normal((ch, ch))
    return np.einsum("cd,ndt->nct", A, rng.standard_normal((n, ch, t))) * 1e-6


def _mean_cov(X):
    X = X.astype(np.float64)
    return np.einsum("nct,ndt->cd", X, X) / (X.shape[0] * X.shape[-1])


def test_aligned_windows_have_identity_mean_covariance():
    X = _windows()
    w = np.linalg.eigvalsh(_mean_cov(align(X, reference_matrix(X))))
    np.testing.assert_allclose(w, 1.0, atol=1e-4)


def test_rank_deficient_windows_keep_unit_eigenvalues_and_send_the_rest_to_zero():
    X = _windows(ch=6)
    X[:, -1] = X[:, 0] + X[:, 1]  # one channel is a sum of two others
    w = np.sort(np.linalg.eigvalsh(_mean_cov(align(X, reference_matrix(X)))))
    assert w[0] < 1e-3
    np.testing.assert_allclose(w[1:], 1.0, atol=1e-4)
    assert np.isfinite(reference_matrix(X)).all()


def test_each_subject_is_aligned_with_its_own_reference():
    rng = np.random.default_rng(1)
    a = _windows(seed=2, mix=rng.standard_normal((8, 8)))
    b = _windows(seed=3, mix=5 * rng.standard_normal((8, 8)))
    X = np.concatenate([a, b])
    subjects = np.array(["s1"] * len(a) + ["s2"] * len(b))
    out = align_by_subject(X, subjects)
    for s in ("s1", "s2"):
        w = np.linalg.eigvalsh(_mean_cov(out[subjects == s]))
        np.testing.assert_allclose(w, 1.0, atol=1e-4)


def test_reference_refuses_an_empty_set():
    with pytest.raises(ValueError):
        reference_matrix(np.empty((0, 8, 10)))
