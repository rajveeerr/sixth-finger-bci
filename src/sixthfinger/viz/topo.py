"""Topographies and time-frequency maps of ERD/ERS."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import mne
import numpy as np

from sixthfinger.config import DataConfig
from sixthfinger.data.channels import mirror_if_needed
from sixthfinger.data.epochs import cut_run
from sixthfinger.data.loading import list_processed_runs

BANDS = {"mu": (8.0, 13.0), "beta": (13.0, 30.0)}
TFR_FREQS = np.arange(6.0, 32.0, 1.0)
# Cut wider than shown so the wavelets' edge effects fall outside the plotted -1..5 s.
PAD_S = 1.0
SHOW_TMIN, SHOW_TMAX = -1.0, 5.0
BASELINE = (-1.0, 0.0)  # the second before the cue, as in the dataset paper
DECIM = 5  # 250 Hz -> 50 Hz after the transform; ERD changes over hundreds of ms


def cue_windows(
    subject: str, session: str, cfg: DataConfig, processed: Path, mirror: bool = True
) -> tuple[np.ndarray, np.ndarray]:
    """Long windows around each imagery cue, cut on the fly (never cached).

    Returns X: (n, 40, n_times) float32 volts from SHOW_TMIN - PAD_S to SHOW_TMAX + PAD_S
    around the cue, and y: (n,) label ids (1 = AH, 2 = SF).
    """
    window = cfg.window.model_copy(update={"tmin": SHOW_TMIN - PAD_S, "tmax": SHOW_TMAX + PAD_S})
    long_cfg = cfg.model_copy(update={"window": window})
    X, y = [], []
    for r in list_processed_runs(processed):
        if r.subject != subject or r.session != session:
            continue
        if cfg.is_run_excluded(subject, session, r.run):
            continue
        rows, _ = cut_run(r.path, long_cfg)
        for x, label, _, _ in rows:
            if label != 0:
                X.append(x)
                y.append(label)
    if not X:
        return np.empty((0, len(cfg.channels.keep), 0), np.float32), np.empty(0, np.int64)
    X = np.stack(X)
    if mirror:
        X = mirror_if_needed(X, subject, cfg.channels.keep)
    return X, np.asarray(y, np.int64)


def erd_timefreq(X: np.ndarray, sfreq: float = 250.0) -> tuple[np.ndarray, np.ndarray]:
    """Mean ERD% over windows: (ch, freq, time) relative to the pre-cue second.

    Power is averaged over windows before the baseline division (the usual ERD
    definition), so single noisy trials cannot dominate through a tiny baseline.
    """
    power = mne.time_frequency.tfr_array_morlet(
        X.astype(np.float64),
        sfreq=sfreq,
        freqs=TFR_FREQS,
        n_cycles=TFR_FREQS / 2.0,
        output="avg_power",
        decim=DECIM,
        n_jobs=1,
        verbose="error",
    )
    times = np.arange(power.shape[-1]) * DECIM / sfreq + SHOW_TMIN - PAD_S
    keep = (times >= SHOW_TMIN - 1e-9) & (times < SHOW_TMAX)
    power, times = power[..., keep], times[keep]
    in_base = (times >= BASELINE[0]) & (times < BASELINE[1])
    base = power[..., in_base].mean(axis=-1, keepdims=True)
    return 100.0 * (power - base) / base, times


def band_mean(erd: np.ndarray, times: np.ndarray, band: tuple[float, float], t0=1.0, t1=5.0):
    """Mean ERD% per channel in a band over [t0, t1) s after the cue."""
    f = (band[0] <= TFR_FREQS) & (band[1] >= TFR_FREQS)
    t = (times >= t0) & (times < t1)
    return erd[:, f][:, :, t].mean(axis=(1, 2))


def montage_info(channels: list[str], sfreq: float = 250.0) -> mne.Info:
    info = mne.create_info(list(channels), sfreq, "eeg")
    info.set_montage(mne.channels.make_standard_montage("colin27_1005"))
    return info


def band_topomap(values: np.ndarray, info: mne.Info, ax: plt.Axes, title: str, vlim=50.0):
    im, _ = mne.viz.plot_topomap(
        values, info, axes=ax, show=False, cmap="RdBu_r", vlim=(-vlim, vlim), contours=4
    )
    ax.set_title(title)
    return im
