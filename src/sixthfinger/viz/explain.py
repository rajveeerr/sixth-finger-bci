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


def eegnet_patterns(net, X: np.ndarray, batch: int = 50) -> np.ndarray:
    """Haufe patterns (n_spatial_filters, channels) of a braindecode EEGNet's depthwise spatial
    filters on network inputs X (n, channels, times).

    Spatial filter j sees temporal feature j // D (grouped convolution, D filters per
    feature); its pattern uses the channel covariance of that feature's map, the output of
    `bnorm_temporal`, which is exactly what the spatial filters receive.
    """
    import torch

    seen: list = []
    hook = net.bnorm_temporal.register_forward_hook(lambda _m, _i, out: seen.append(out.detach()))
    n_feat, n_ch = net.conv_temporal.out_channels, X.shape[1]
    total, s, ss = 0, np.zeros((n_feat, n_ch)), np.zeros((n_feat, n_ch, n_ch))
    net.eval()
    try:
        with torch.no_grad():
            for start in range(0, len(X), batch):
                seen.clear()
                net(torch.from_numpy(np.ascontiguousarray(X[start : start + batch], np.float32)))
                xb = seen[0].double().numpy().transpose(1, 2, 0, 3).reshape(n_feat, n_ch, -1)
                total += xb.shape[2]
                s += xb.sum(axis=2)
                ss += np.einsum("fct,fdt->fcd", xb, xb)
    finally:
        hook.remove()
    mean = s / total
    covs = (ss - total * np.einsum("fc,fd->fcd", mean, mean)) / (total - 1)
    W = net.conv_spatial.weight.detach().double().numpy()[:, 0, :, 0]  # (F1 * D, channels)
    depth = W.shape[0] // n_feat
    return np.stack([haufe_patterns(W[j], covs[j // depth])[0] for j in range(len(W))])
