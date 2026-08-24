"""Read the dataset's EEGLAB files into MNE objects."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import mne
import numpy as np
from pymatreader import read_mat

from sixthfinger.data.channels import CHANNELS_40

FILENAME_RE = re.compile(
    r"^(?P<subject>sub-\d{2})_(?P<group>[BT])_(?P<session>pre|post|follow)_(?P<run>\d{2})_"
    r"(?P<kind>eeg|original)\.(?P<ext>mat|set)$"
)

BOUNDARY = "BAD_boundary"
MI_CODES = ("1", "2", "3")


@dataclass(frozen=True)
class RunInfo:
    subject: str
    group: str
    session: str
    run: str
    path: Path

    @property
    def key(self) -> str:
        return f"{self.subject}_ses-{self.session}_run-{self.run}"


def parse_run_filename(path: Path) -> RunInfo:
    m = FILENAME_RE.match(path.name)
    if m is None:
        raise ValueError(f"Unexpected file name: {path.name}")
    return RunInfo(m["subject"], m["group"], m["session"], m["run"], path)


def list_processed_runs(processed_dir: Path) -> list[RunInfo]:
    runs = [parse_run_filename(p) for p in processed_dir.glob("sub-*/*/sub-*_eeg.mat")]
    return sorted(
        runs, key=lambda r: (r.subject, ("pre", "post", "follow").index(r.session), r.run)
    )


def _event_code(value: object) -> str:
    """EEGLAB stores event types as strings or numbers depending on how they were created."""
    if isinstance(value, str):
        return value.strip()
    as_float = float(value)  # type: ignore[arg-type]
    return str(int(as_float)) if as_float.is_integer() else str(as_float)


@dataclass(frozen=True)
class EEGLABRecord:
    data_uv: np.ndarray  # (n_channels, n_times), microvolts as stored
    ch_names: list[str]
    sfreq: float
    event_codes: list[str]
    event_samples: np.ndarray  # 0-based sample index of each event


def read_eeglab_mat(path: Path) -> EEGLABRecord:
    """Read a preprocessed ``*_eeg.mat`` (MATLAB v7.3 file holding an EEGLAB EEG struct)."""
    eeg = read_mat(str(path))["EEG"]
    data = np.asarray(eeg["data"], dtype=np.float32)
    if data.ndim != 2:
        raise ValueError(f"{path.name}: expected continuous data, got shape {data.shape}")
    labels = eeg["chanlocs"]["labels"]
    ch_names = [labels] if isinstance(labels, str) else list(labels)
    if data.shape[0] != len(ch_names):
        raise ValueError(f"{path.name}: {data.shape[0]} rows but {len(ch_names)} channel labels")
    ev = eeg["event"]
    types = ev["type"] if isinstance(ev["type"], list) else [ev["type"]]
    latencies = np.atleast_1d(np.asarray(ev["latency"], dtype=float))
    # EEGLAB latencies are 1-based (MATLAB indexing).
    samples = np.rint(latencies - 1).astype(np.int64)
    return EEGLABRecord(
        data_uv=data,
        ch_names=ch_names,
        sfreq=float(eeg["srate"]),
        event_codes=[_event_code(t) for t in types],
        event_samples=samples,
    )


def record_to_raw(
    rec: EEGLABRecord,
    channels: tuple[str, ...] | list[str] = CHANNELS_40,
    scale_to_volts: float = 1e-6,
    set_montage: bool = True,
) -> mne.io.RawArray:
    """Build an MNE Raw with the requested channels (in that order), in volts.

    Events become annotations: '1', '2', '3' at the cue onsets and BAD_boundary where
    EEGLAB cut data out, so MNE's reject_by_annotation also skips the discontinuities.
    """
    missing = [c for c in channels if c not in rec.ch_names]
    if missing:
        raise ValueError(f"Channels missing from file: {missing}")
    idx = [rec.ch_names.index(c) for c in channels]
    data = rec.data_uv[idx].astype(np.float64) * scale_to_volts
    info = mne.create_info(list(channels), rec.sfreq, ch_types="eeg")
    raw = mne.io.RawArray(data, info, verbose="error")
    onsets, durations, descriptions = [], [], []
    for code, sample in zip(rec.event_codes, rec.event_samples, strict=True):
        onsets.append(sample / rec.sfreq)
        if code == "boundary":
            durations.append(1.0 / rec.sfreq)
            descriptions.append(BOUNDARY)
        else:
            durations.append(0.0)
            descriptions.append(code)
    raw.set_annotations(mne.Annotations(onsets, durations, descriptions))
    if set_montage:
        # standard_1005 is deprecated from MNE 1.13; colin27_1005 is its replacement.
        montage = mne.channels.make_standard_montage("colin27_1005")
        raw.set_montage(montage, on_missing="warn", verbose="error")
    return raw


def load_processed_run(
    path: Path,
    channels: tuple[str, ...] | list[str] = CHANNELS_40,
    scale_to_volts: float = 1e-6,
) -> tuple[mne.io.RawArray, RunInfo]:
    return record_to_raw(read_eeglab_mat(path), channels, scale_to_volts), parse_run_filename(path)


def load_raw_run(path: Path) -> mne.io.BaseRaw:
    """Read an unprocessed ``*_original.set`` file.

    The .set headers contain characters that MNE's default uint16 codec rejects with
    "buffer is too small for requested array"; latin1 reads them correctly.
    """
    return mne.io.read_raw_eeglab(path, preload=True, uint16_codec="latin1", verbose="error")
