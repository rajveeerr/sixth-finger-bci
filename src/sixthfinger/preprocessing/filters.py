"""Band-pass filters and the mu ERSP feature applied to EEG windows."""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, hilbert, sosfiltfilt
from sklearn.base import BaseEstimator, TransformerMixin


def _sos(low: float, high: float, sfreq: float, order: int) -> np.ndarray:
    return butter(order, [low, high], btype="bandpass", fs=sfreq, output="sos")


def bandpass(X: np.ndarray, low: float, high: float, sfreq: float, order: int = 4) -> np.ndarray:
    """Zero-phase Butterworth band-pass along the last axis; returns float32."""
    return sosfiltfilt(_sos(low, high, sfreq, order), X, axis=-1).astype(np.float32)


class BandPass(BaseEstimator, TransformerMixin):
    """Stateless band-pass step, so a filter bank can sit inside a scikit-learn pipeline."""

    def __init__(self, low: float, high: float, sfreq: float = 250.0, order: int = 4):
        self.low = low
        self.high = high
        self.sfreq = sfreq
        self.order = order

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        return bandpass(X, self.low, self.high, self.sfreq, self.order)


class FilterBank(BaseEstimator, TransformerMixin):
    """Stateless: X (n, n_channels, n_times) -> (n, n_bands, n_channels, n_times), float32."""

    def __init__(self, bands, sfreq: float = 250.0, order: int = 4):
        self.bands = bands
        self.sfreq = sfreq
        self.order = order

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        return np.stack(
            [bandpass(X, lo, hi, self.sfreq, self.order) for lo, hi in self.bands], axis=1
        )


def ersp_db(
    X_long: np.ndarray,
    sfreq: float,
    band: tuple[float, float],
    baseline: tuple[int, int],
    keep: tuple[int, int],
    order: int = 4,
) -> np.ndarray:
    """Band power envelope in dB relative to each window's own baseline.

    Each window is divided by its own baseline power, so the feature has no fitted
    parameters and nothing passes from one window to another.

    Args:
        X_long: (n, n_channels, n_times) volts, cut wide enough to hold baseline and keep.
        baseline, keep: sample ranges [start, stop) within X_long.

    Returns:
        (n, n_channels, keep[1] - keep[0]) float32, dB.
    """
    filtered = sosfiltfilt(_sos(band[0], band[1], sfreq, order), X_long, axis=-1)
    power = np.abs(hilbert(filtered, axis=-1)) ** 2
    base = power[..., baseline[0] : baseline[1]].mean(axis=-1, keepdims=True)
    return (10.0 * np.log10(power[..., keep[0] : keep[1]] / base)).astype(np.float32)
