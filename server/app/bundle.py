"""Demo bundle: manifest, held-out trials and the exported decoder."""

import hashlib
import json
from functools import cached_property
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION = 1


class ClassInfo(BaseModel):
    id: int
    name: str
    label: str
    command: str


class ModelInfo(BaseModel):
    file: str
    sha256: str
    input_name: str = "eeg"
    output_name: str = "probs"
    output: Literal["probabilities", "logits"] = "probabilities"
    n_channels: int
    n_times: int
    name: str
    method: str
    trained_on: str
    notes: str = ""


class PreprocessOp(BaseModel):
    op: Literal["scale", "spatial_filter", "channel_standardize"]
    factor: float | None = None
    matrix: list[list[float]] | None = None
    mean: list[float] | None = None
    std: list[float] | None = None


class Encoding(BaseModel):
    dtype: Literal["int16", "float32"]
    scale_uv: float = 1.0


class Window(BaseModel):
    start_s: float = 1.0
    end_s: float = 5.0


class TrialInfo(BaseModel):
    index: int
    uid: str
    label: int
    cue_onset_s: float
    n_samples: int
    offset_bytes: int


class Source(BaseModel):
    dataset: str
    doi: str
    license: str
    subject: str
    session: str
    runs: list[int]
    attribution: str


class Manifest(BaseModel):
    schema_version: int
    created_at: str
    synthetic: bool
    source: Source
    sfreq: float
    channels: list[str]
    display_channels: list[str]
    display_decimation: int = 2
    units: Literal["uV"] = "uV"
    classes: list[ClassInfo]
    window: Window
    model: ModelInfo
    preprocessing: list[PreprocessOp] = Field(default_factory=list)
    encoding: Encoding
    trials_file: str
    trials_sha256: str
    predictions_file: str
    trials: list[TrialInfo]

    @model_validator(mode="after")
    def _check(self) -> "Manifest":
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unsupported bundle schema {self.schema_version}")
        if len(self.channels) != self.model.n_channels:
            raise ValueError("channel list and model input disagree")
        missing = set(self.display_channels) - set(self.channels)
        if missing:
            raise ValueError(f"display channels not in bundle: {sorted(missing)}")
        if [c.id for c in self.classes] != list(range(len(self.classes))):
            raise ValueError("class ids must be 0..n-1 in order")
        if not self.trials:
            raise ValueError("bundle has no trials")
        return self


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def apply_preprocessing(window_uv: np.ndarray, ops: list[PreprocessOp]) -> np.ndarray:
    """Turn a (n_channels, n_times) window in microvolts into model input."""
    x = window_uv.astype(np.float32, copy=True)
    for op in ops:
        if op.op == "scale":
            x *= np.float32(op.factor)
        elif op.op == "spatial_filter":
            x = np.asarray(op.matrix, dtype=np.float32) @ x
        elif op.op == "channel_standardize":
            mean = np.asarray(op.mean, dtype=np.float32)[:, None]
            std = np.asarray(op.std, dtype=np.float32)[:, None]
            x = (x - mean) / std
    return x


class Bundle:
    def __init__(self, directory: Path, verify: bool = True) -> None:
        self.directory = Path(directory)
        manifest_path = self.directory / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"no manifest.json in {self.directory}")
        self.manifest = Manifest.model_validate_json(manifest_path.read_text())
        self.model_path = self.directory / self.manifest.model.file
        self.trials_path = self.directory / self.manifest.trials_file
        if verify:
            self._verify()

    def _verify(self) -> None:
        if sha256_of(self.model_path) != self.manifest.model.sha256:
            raise ValueError("model file does not match the manifest checksum")
        if sha256_of(self.trials_path) != self.manifest.trials_sha256:
            raise ValueError("trials file does not match the manifest checksum")
        itemsize = np.dtype(self.manifest.encoding.dtype).itemsize
        n_ch = len(self.manifest.channels)
        expected = sum(t.n_samples * n_ch * itemsize for t in self.manifest.trials)
        if self.trials_path.stat().st_size != expected:
            raise ValueError("trials file size does not match the manifest")

    @cached_property
    def _raw(self) -> np.ndarray:
        return np.fromfile(
            self.trials_path, dtype=np.dtype(self.manifest.encoding.dtype).newbyteorder("<")
        )

    def trial_data(self, index: int) -> np.ndarray:
        """Trial as (n_channels, n_samples) float32 microvolts."""
        info = self.manifest.trials[index]
        itemsize = np.dtype(self.manifest.encoding.dtype).itemsize
        start = info.offset_bytes // itemsize
        n_ch = len(self.manifest.channels)
        flat = self._raw[start : start + n_ch * info.n_samples]
        data = flat.reshape(n_ch, info.n_samples).astype(np.float32)
        return data * np.float32(self.manifest.encoding.scale_uv)

    @cached_property
    def predictions(self) -> dict:
        return json.loads((self.directory / self.manifest.predictions_file).read_text())

    @property
    def n_trials(self) -> int:
        return len(self.manifest.trials)

    def display_indices(self) -> list[int]:
        return [self.manifest.channels.index(name) for name in self.manifest.display_channels]
