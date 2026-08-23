from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import scipy.io

from sixthfinger.data.channels import CHANNELS_40, DROPPED_CHANNELS

SFREQ = 250.0
FILE_CHANNELS = (*DROPPED_CHANNELS, *CHANNELS_40)


def synthetic_events(n_trials: int = 4, first: int = 750, seed: int = 0) -> list[tuple[str, int]]:
    """Rest marker, then an MI cue 8.57 s later, next trial about 7 s after that.

    The spacing copies what the real recordings show (not the 8 s in the paper).
    Latencies are 1-based like EEGLAB.
    """
    rng = np.random.default_rng(seed)
    codes = rng.permutation(["2", "3"] * (n_trials // 2) + ["2"] * (n_trials % 2))
    events = [("boundary", 1)]
    t = first
    for code in codes:
        events.append(("1", t + 1))
        events.append((str(code), t + 2142 + 1))
        t += 2142 + 1750
    return events


def write_eeglab_mat(
    path: Path,
    *,
    n_times: int | None = None,
    events: list[tuple[str, int]] | None = None,
    channels: tuple[str, ...] = FILE_CHANNELS,
    seed: int = 0,
) -> np.ndarray:
    """Write a MATLAB v5 file shaped like the dataset's EEG struct; returns the data (µV)."""
    events = events if events is not None else synthetic_events(seed=seed)
    if n_times is None:
        n_times = max(lat for _, lat in events) + int(7 * SFREQ)
    rng = np.random.default_rng(seed)
    data = (rng.standard_normal((len(channels), n_times)) * 5.0).astype(np.float32)
    chanlocs = np.zeros((1, len(channels)), dtype=[("labels", object)])
    for i, name in enumerate(channels):
        chanlocs[0, i]["labels"] = name
    ev = np.zeros(
        (1, len(events)), dtype=[("type", object), ("latency", object), ("duration", object)]
    )
    for i, (code, lat) in enumerate(events):
        ev[0, i]["type"] = code
        ev[0, i]["latency"] = float(lat)
        ev[0, i]["duration"] = 0.0
    eeg = {
        "data": data,
        "srate": SFREQ,
        "nbchan": float(len(channels)),
        "pnts": float(n_times),
        "trials": 1.0,
        "chanlocs": chanlocs,
        "event": ev,
        "ref": "average",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    scipy.io.savemat(path, {"EEG": eeg}, do_compression=False)
    return data


@pytest.fixture
def mat_run(tmp_path: Path) -> tuple[Path, np.ndarray]:
    path = tmp_path / "processed" / "sub-03" / "pre" / "sub-03_B_pre_01_eeg.mat"
    data = write_eeglab_mat(path)
    return path, data


@pytest.fixture
def processed_tree(tmp_path: Path) -> Path:
    root = tmp_path / "processed"
    for subject, group in (("sub-01", "B"), ("sub-07", "T")):
        for session in ("pre", "post"):
            for run in ("01", "02"):
                name = f"{subject}_{group}_{session}_{run}_eeg.mat"
                write_eeglab_mat(root / subject / session / name, seed=int(run))
    return root
