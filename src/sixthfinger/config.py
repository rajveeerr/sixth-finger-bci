"""Typed configuration loaded from the YAML files in configs/."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from sixthfinger.paths import get_paths


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ArchiveCfg(Strict):
    file_id: int
    filename: str
    size_bytes: int
    md5: str = Field(pattern=r"^[0-9a-f]{32}$")
    expected_files: int
    extract_to: Literal["processed", "source"]


class FigshareCfg(Strict):
    article_id: int
    version: int
    download_url: str
    api_url: str
    archives: dict[str, ArchiveCfg]
    metadata_files: list[str]

    def url_for(self, archive: str) -> str:
        return self.download_url.format(file_id=self.archives[archive].file_id)

    @property
    def article_api(self) -> str:
        return self.api_url.format(article_id=self.article_id)


class SignalCfg(Strict):
    sfreq: float
    units_in_file: Literal["microvolt"]
    scale_to_volts: float
    car40: bool = False


class ChannelsCfg(Strict):
    keep: list[str]
    drop: list[str]
    mirror_pairs: list[tuple[str, str]]
    mirror: bool = False

    @model_validator(mode="after")
    def _pairs_in_keep(self) -> ChannelsCfg:
        missing = {c for pair in self.mirror_pairs for c in pair} - set(self.keep)
        if missing:
            raise ValueError(f"mirror_pairs name channels not in keep: {sorted(missing)}")
        if len(set(self.keep)) != len(self.keep):
            raise ValueError("duplicate channel in keep")
        return self


class LabelCfg(Strict):
    id: int
    name: Literal["rest", "affected_hand", "sixth_finger"]
    short: str
    event_code: str
    command: str


class WindowCfg(Strict):
    tmin: float
    tmax: float
    drop_if_boundary_inside: bool = True

    @model_validator(mode="after")
    def _ordered(self) -> WindowCfg:
        if self.tmax <= self.tmin:
            raise ValueError("window tmax must be greater than tmin")
        return self


class SubjectsCfg(Strict):
    ids: list[str]
    sessions: list[Literal["pre", "post", "follow"]]
    runs: list[str]
    missing_sessions: dict[str, list[str]]
    left_hemiplegic: list[str]
    bci_group: list[str]


class SessionExclusion(Strict):
    subject: str
    session: str
    reason: str


class RunExclusion(Strict):
    subject: str
    session: str
    run: str
    reason: str


class LinkedSubjects(Strict):
    members: list[str]
    reason: str


class ExclusionsCfg(Strict):
    sessions: list[SessionExclusion] = []
    runs: list[RunExclusion] = []
    linked_subjects: list[LinkedSubjects] = []


class PathsCfg(Strict):
    processed_glob: str


class DataConfig(Strict):
    figshare: FigshareCfg
    signal: SignalCfg
    channels: ChannelsCfg
    labels: list[LabelCfg]
    window: WindowCfg
    subjects: SubjectsCfg
    exclusions: ExclusionsCfg
    paths: PathsCfg

    @field_validator("labels")
    @classmethod
    def _labels_contiguous(cls, v: list[LabelCfg]) -> list[LabelCfg]:
        if [lab.id for lab in v] != list(range(len(v))):
            raise ValueError("label ids must be 0..n-1 in order")
        return v

    @property
    def n_times(self) -> int:
        return round((self.window.tmax - self.window.tmin) * self.signal.sfreq)

    @property
    def label_by_code(self) -> dict[str, LabelCfg]:
        return {lab.event_code: lab for lab in self.labels}

    @property
    def label_by_name(self) -> dict[str, LabelCfg]:
        return {lab.name: lab for lab in self.labels}

    def is_excluded(self, subject: str, session: str) -> bool:
        return any(e.subject == subject and e.session == session for e in self.exclusions.sessions)

    def is_run_excluded(self, subject: str, session: str, run: str) -> bool:
        return self.is_excluded(subject, session) or any(
            e.subject == subject and e.session == session and e.run == run
            for e in self.exclusions.runs
        )

    def sessions_for(self, subject: str) -> list[str]:
        return [
            s
            for s in self.subjects.sessions
            if subject not in self.subjects.missing_sessions.get(s, [])
            and not self.is_excluded(subject, s)
        ]

    def split_group(self, subject: str) -> str:
        """Group id for cross-subject splits; linked subjects share one id."""
        for link in self.exclusions.linked_subjects:
            if subject in link.members:
                return "+".join(sorted(link.members))
        return subject


class ScenarioCfg(Strict):
    description: str
    full_classes: list[str]
    budget_classes: list[str]


class WithinSessionCfg(Strict):
    protocols: list[Literal["paper_replica", "cv_leakfree", "loro", "chrono"]]
    cv_folds: int
    cv_repeats: int
    chrono_train_runs: list[str]
    chrono_test_runs: list[str]


class CalibrationCfg(Strict):
    confirmatory_session: str
    replication_session: str
    pool_runs: list[str]
    test_runs: list[str]
    k_grid: list[int]
    draws_classical: int
    draws_deep: int
    seed_base: int
    chrono_draw: bool
    trial_seconds: float
    scenarios: dict[str, ScenarioCfg]
    eval_tasks: list[str]

    @model_validator(mode="after")
    def _disjoint_runs(self) -> CalibrationCfg:
        if set(self.pool_runs) & set(self.test_runs):
            raise ValueError("calibration pool runs and test runs overlap")
        if self.k_grid != sorted(set(self.k_grid)):
            raise ValueError("k_grid must be sorted and unique")
        return self


class CrossSubjectCfg(Strict):
    pretrain_validation_subjects: int


class MetricsCfg(Strict):
    primary: str
    report: list[str]
    usable_threshold_2class: float
    usable_threshold_3class: list[float]


class StatsCfg(Strict):
    alpha: float
    correction: Literal["holm", "bonferroni", "fdr_bh"]
    bootstrap_resamples: int
    bootstrap_seed: int
    friedman_k: list[int]


class ProtocolConfig(Strict):
    tasks: dict[str, list[str]]
    within_session: WithinSessionCfg
    calibration: CalibrationCfg
    cross_subject: CrossSubjectCfg
    dev_subjects: list[str]
    metrics: MetricsCfg
    stats: StatsCfg


def _read_yaml(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f)


def load_data_config(path: Path | None = None) -> DataConfig:
    return DataConfig.model_validate(_read_yaml(path or get_paths().configs / "data.yaml"))


def load_protocol_config(path: Path | None = None) -> ProtocolConfig:
    return ProtocolConfig.model_validate(_read_yaml(path or get_paths().configs / "protocol.yaml"))


def config_hash(*configs: BaseModel) -> str:
    """Stable short hash of resolved configs, stored with every result row."""
    payload = json.dumps([c.model_dump(mode="json") for c in configs], sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
