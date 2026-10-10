"""Euclidean alignment of EEG windows (He and Wu, 2020).

Each subject's windows are whitened by the inverse square root of that subject's mean
covariance, so every subject's average covariance becomes the identity and subjects look
alike to a decoder trained on others.
"""

from __future__ import annotations

import numpy as np


def reference_matrix(X: np.ndarray, rel_floor: float = 1e-6) -> np.ndarray:
    """Inverse square root of the mean trial covariance. X: (n, ch, t), volts.

    Computed in float64 with eigh: some preprocessed sessions are rank-deficient (common
    average reference and removed ICA components), so tiny eigenvalues are floored at
    rel_floor times the largest. float32 or a regularised fractional power gave errors of
    0.6 to 8000 on the same data during setup.
    """
    X = np.asarray(X, dtype=np.float64)
    if X.ndim != 3 or X.shape[0] == 0:
        raise ValueError(f"expected (n, ch, t) windows, got shape {X.shape}")
    R = np.einsum("nct,ndt->cd", X, X) / (X.shape[0] * X.shape[-1])
    w, V = np.linalg.eigh(R)
    w = np.maximum(w, rel_floor * w.max())
    return (V @ np.diag(w**-0.5) @ V.T).astype(np.float32)


def align(X: np.ndarray, R_inv_sqrt: np.ndarray) -> np.ndarray:
    """Apply a reference matrix to windows X: (n, ch, t); returns float32."""
    out = np.einsum("cd,ndt->nct", R_inv_sqrt.astype(np.float64), np.asarray(X, np.float64))
    return out.astype(np.float32)


def align_by_subject(X: np.ndarray, subjects: np.ndarray) -> np.ndarray:
    """Align each subject's windows with that subject's own reference (source data)."""
    out = np.empty_like(X, dtype=np.float32)
    for subject in np.unique(subjects):
        sel = subjects == subject
        out[sel] = align(X[sel], reference_matrix(X[sel]))
    return out
