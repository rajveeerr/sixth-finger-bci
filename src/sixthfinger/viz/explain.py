"""What the decoders look at (P09 Study 5): CSP patterns, Haufe patterns of EEGNet's spatial
filters, and the share of pattern weight on channel groups.

Filters are how channels are combined; patterns are how a source appears on the scalp, and
only patterns are read as topographies (Haufe et al., 2014).
"""

from __future__ import annotations

import numpy as np

FRONTAL = ["AF3", "AF4", "F5", "F6"]  # closest to the eyes (step 4.4, point 4)
PARIETO_OCCIPITAL = ["POz", "PO3", "PO4", "PO5", "PO6"]  # visual-cue check (point 5)


def channel_covariance(X: np.ndarray, batch: int = 256) -> np.ndarray:
    """Covariance over channels of (n, ch, t) data, accumulated in batches.

    np.cov on all windows at once needs several float64 copies of the data (10 000 windows:
    about 3.2 GB each), too much for the 8 GB Mac.
    """
    n_ch = X.shape[1]
    total, s, ss = 0, np.zeros(n_ch), np.zeros((n_ch, n_ch))
    for start in range(0, len(X), batch):
        xb = X[start : start + batch].astype(np.float64).transpose(1, 0, 2).reshape(n_ch, -1)
        total += xb.shape[1]
        s += xb.sum(axis=1)
        ss += xb @ xb.T
    mean = s / total
    return (ss - total * np.outer(mean, mean)) / (total - 1)


def haufe_patterns(W: np.ndarray, cov_x: np.ndarray) -> np.ndarray:
    """Patterns (n_filters, n_channels) of spatial filters W (n_filters, n_channels) applied to
    data with channel covariance cov_x: A = cov_x Wᵀ (W cov_x Wᵀ)⁻¹."""
    W = np.atleast_2d(W)
    cov_s = W @ cov_x @ W.T
    return (cov_x @ W.T @ np.linalg.pinv(cov_s)).T


def normalised_abs(patterns: np.ndarray) -> np.ndarray:
    """Each pattern's absolute values over its largest, so patterns of any scale average."""
    a = np.abs(np.atleast_2d(patterns))
    return a / a.max(axis=1, keepdims=True)


def weight_share(pattern: np.ndarray, channels: list[str], group: list[str]) -> float:
    """Share of a (non-negative) map's total weight on the channels of `group`."""
    idx = [channels.index(c) for c in group]
    return float(pattern[idx].sum() / pattern.sum())
