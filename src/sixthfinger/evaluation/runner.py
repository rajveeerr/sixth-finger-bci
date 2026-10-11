"""Runs an experiment config and writes scores.parquet (results contract, conventions 6)."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import subprocess
import time
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
import yaml
from joblib import Parallel, delayed
from pydantic import Field
from sklearn.base import clone

from sixthfinger.config import (
    DataConfig,
    ProtocolConfig,
    Strict,
    config_hash,
    load_data_config,
    load_protocol_config,
)
from sixthfinger.data.epochs import load_windows, manifest_sha, recut
from sixthfinger.evaluation.calibration import REST_ID, draw_calibration_set
from sixthfinger.evaluation.leakage import assert_no_leakage
from sixthfinger.evaluation.metrics import SF, score
from sixthfinger.evaluation.splits import (
    Split,
    chrono_split,
    cv_leakfree_splits,
    loro_splits,
    n_cv_folds,
    paper_replica_splits,
)
from sixthfinger.models.registry import REGISTRY, Batch, UndefinedCell, make_method
from sixthfinger.paths import current_git_sha, get_paths
from sixthfinger.preprocessing.filters import ersp_db

log = logging.getLogger(__name__)

UNIT_KEYS = [
    "experiment",
    "protocol",
    "scenario",
    "task",
    "method",
    "feature",
    "subject",
    "session",
    "k",
    "draw",
    "fold",
]
METRIC_KEYS = [
    "bal_acc",
    "acc",
    "f1_macro",
    "kappa",
    "sf_recall",
    "sf_precision",
    "auc_sf",
    "confusion",
]
QUICK_K_GRID = [0, 2, 20]
QUICK_DRAWS = 2
AH_PROXY = "ah_proxy"
AH = 1


class ExperimentConfig(Strict):
    name: str
    protocol: Literal["within_session", "calibration"]
    tasks: list[str]
    sessions: list[Literal["pre", "post", "follow"]]
    subjects: list[str] | Literal["all"]
    methods: list[str]
    mirror: bool = False
    features: list[str] = Field(default_factory=lambda: ["bandpower"])
    within_protocols: list[Literal["paper_replica", "cv_leakfree", "loro", "chrono"]] = Field(
        default_factory=list
    )
    scenarios: list[str] = Field(default_factory=list)
    k_grid: list[int] | Literal["from_protocol"] = "from_protocol"
    draws: int | Literal["from_protocol"] = "from_protocol"
    # Training seeds of a within-session experiment (deep training is noisy: P07 reports
    # the mean over a fixed set). Each seed is its own unit, stored as `draw`; without
    # seeds every fold is fitted once with the protocol's seed_base and `draw` stays empty.
    seeds: list[int] | None = None


def load_experiment(path: Path, proto: ProtocolConfig) -> ExperimentConfig:
    exp = ExperimentConfig.model_validate(yaml.safe_load(Path(path).read_text()))
    unknown = (
        [t for t in exp.tasks if t not in proto.tasks]
        + [s for s in exp.scenarios if s not in proto.calibration.scenarios]
        + [p for p in exp.within_protocols if p not in proto.within_session.protocols]
    )
    if unknown:
        raise ValueError(f"{path}: not in configs/protocol.yaml: {unknown}")
    if exp.protocol == "within_session" and not exp.within_protocols:
        raise ValueError(f"{path}: a within_session experiment needs within_protocols")
    if exp.protocol == "calibration" and not exp.scenarios:
        raise ValueError(f"{path}: a calibration experiment needs scenarios")
    return exp


def resolve(
    exp: ExperimentConfig,
    proto: ProtocolConfig,
    data_cfg: DataConfig,
    subjects: list[str] | None = None,
    methods: list[str] | None = None,
    quick: bool = False,
) -> ExperimentConfig:
    """Replace the `from_protocol`/`all` placeholders and apply the command-line subsets."""
    update: dict = {}
    if exp.k_grid == "from_protocol":
        update["k_grid"] = list(proto.calibration.k_grid)
    all_subjects = list(data_cfg.subjects.ids) if exp.subjects == "all" else list(exp.subjects)
    update["subjects"] = _subset(all_subjects, subjects, "subject")
    update["methods"] = _subset(list(exp.methods), methods, "method")
    if quick:
        update.update(name=f"{exp.name}_quick", k_grid=QUICK_K_GRID, draws=QUICK_DRAWS)
    exp = exp.model_copy(update=update)
    if missing := [m for m in exp.methods if m not in REGISTRY]:
        raise KeyError(f"Methods not in the registry: {missing}; known: {sorted(REGISTRY)}")
    return exp


def _subset(allowed: list[str], wanted: list[str] | None, what: str) -> list[str]:
    # An unknown name is an error, never silently skipped: a typo must not shrink a study.
    if wanted is None:
        return allowed
    if bad := [w for w in wanted if w not in allowed]:
        raise ValueError(f"{what} {bad} not in the experiment config's list {allowed}")
    return [a for a in allowed if a in wanted]


def _norm(value) -> str:
    """Unit-key component as a string, so ints, floats from parquet and None compare equal."""
    if value is None or (isinstance(value, float) and math.isnan(value)) or value is pd.NA:
        return ""
    if isinstance(value, float | np.floating) and float(value).is_integer():
        value = int(value)
    return str(value)


def unit_key(row: dict) -> tuple[str, ...]:
    return tuple(_norm(row.get(k)) for k in UNIT_KEYS)


def completed_units(path: Path) -> set[tuple[str, ...]]:
    if not path.exists():
        return set()
    done = pd.read_parquet(path, columns=UNIT_KEYS)
    return {unit_key(r) for r in done.to_dict("records")}


@dataclass
class ScoreWriter:
    """Buffers rows and rewrites the parquet atomically, so a crash leaves a whole file."""

    path: Path
    flush_every: int = 50
    rows: list[dict] = field(default_factory=list)
    n_written: int = 0

    def append(self, row: dict) -> None:
        self.rows.append(row)
        if len(self.rows) >= self.flush_every:
            self.flush()

    def flush(self) -> None:
        if not self.rows:
            return
        new = pd.DataFrame(self.rows)
        frames = [pd.read_parquet(self.path)] if self.path.exists() else []
        out = pd.concat([*frames, new], ignore_index=True)
        for col in ("k", "fold"):
            out[col] = pd.to_numeric(out[col]).astype("Int64")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        out.to_parquet(tmp, index=False)
        tmp.replace(self.path)
        self.n_written += len(self.rows)
        self.rows = []


@dataclass
class RunContext:
    exp: ExperimentConfig
    data_cfg: DataConfig
    proto: ProtocolConfig
    X: np.ndarray
    md: pd.DataFrame
    writer: ScoreWriter
    done: set
    provenance: dict
    method_params: dict[str, dict]
    base_hash: str
    processed: Path | None = None

    def skip(self, key: dict) -> bool:
        return unit_key(key) in self.done

    def write(self, key: dict, metrics: dict | None = None, **extra) -> None:
        method = key.get("method")
        params = json.dumps(self.method_params.get(method, {}), sort_keys=True)
        row = {
            **key,
            **(metrics or {k: np.nan for k in METRIC_KEYS}),
            **extra,
            **self.provenance,
            "config_hash": hashlib.sha256((self.base_hash + params).encode()).hexdigest()[:16],
        }
        row.setdefault("reason", None)
        self.writer.append(row)

    def batch(self, rows: pd.DataFrame, labels: bool = True) -> Batch:
        idx = rows.index.to_numpy()
        return Batch(self.X[idx], rows.label.to_numpy() if labels else None, rows)


def method_params(name: str, configs: Path) -> dict:
    """Hyperparameters from configs/models/<name>.yaml (written in P06-P08), if any."""
    path = configs / "models" / f"{name}.yaml"
    if not path.exists():
        return {}
    params = yaml.safe_load(path.read_text()) or {}
    params.pop("method", None)
    return params


def _provenance(epochs_dir: Path) -> dict:
    return {
        "git_sha": current_git_sha(),
        "data_manifest_sha": manifest_sha(epochs_dir),
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def _class_ids(data_cfg: DataConfig, names: Iterable[str]) -> list[int]:
    return sorted(data_cfg.label_by_name[n].id for n in names)


def feature_of(method_name: str) -> str:
    """Input a method reads: the cached windows (`bandpower`) unless the class says otherwise."""
    return getattr(REGISTRY[method_name], "feature", "bandpower")


PREREG_TAG = "prereg-v1"


def require_prereg(subjects: Iterable[str], dev_subjects: Iterable[str], root: Path) -> None:
    """Refuse a calibration run beyond the development subjects before the pre-registration.

    In a git checkout the tag must be an ancestor of HEAD. A Kaggle bundle has no history:
    its build script makes the same check and writes PREREG, which is read instead.
    """
    if set(subjects) <= set(dev_subjects):
        return
    if (root / ".git").exists():
        ok = (
            subprocess.run(
                ["git", "-C", str(root), "merge-base", "--is-ancestor", PREREG_TAG, "HEAD"],
                capture_output=True,
            ).returncode
            == 0
        )
    else:
        stamp = root / "PREREG"
        ok = stamp.is_file() and PREREG_TAG in stamp.read_text().split()
    if not ok:
        raise RuntimeError(
            f"Full-cohort calibration runs need code at or after the {PREREG_TAG} tag (P05)."
        )


def run_experiment(
    config_path: Path,
    subjects: list[str] | None = None,
    methods: list[str] | None = None,
    quick: bool = False,
    *,
    n_jobs: int = 1,
    epochs_dir: Path | None = None,
    runs_dir: Path | None = None,
    processed_dir: Path | None = None,
    data_cfg: DataConfig | None = None,
    proto: ProtocolConfig | None = None,
) -> Path:
    """Run every unit of the experiment that is not in its scores file yet; return the file.

    n_jobs > 1 spreads the subject-sessions of a within-session experiment over processes;
    every fit is the same as with one process, only the row order in the file differs.
    """
    import mne

    mne.set_log_level("ERROR")
    paths = get_paths()
    data_cfg = data_cfg or load_data_config()
    proto = proto or load_protocol_config()
    epochs_dir = epochs_dir or paths.epochs
    exp = resolve(load_experiment(config_path, proto), proto, data_cfg, subjects, methods, quick)
    out_path = (runs_dir or paths.runs) / exp.name / "scores.parquet"
    if exp.protocol == "calibration":
        require_prereg(exp.subjects, proto.dev_subjects, paths.root)
    if exp.protocol == "calibration" and (
        odd := [m for m in exp.methods if feature_of(m) != "bandpower"]
    ):
        raise ValueError(f"The calibration protocol only feeds cached windows; not {odd}")

    needs_source = exp.protocol == "calibration" and any(
        REGISTRY[m].uses_source for m in exp.methods
    )
    # Within a session only the tasks' classes are needed; calibration draws on all three.
    labels = (
        sorted({c for t in exp.tasks for c in _class_ids(data_cfg, proto.tasks[t])})
        if exp.protocol == "within_session"
        else None
    )
    # Without a transfer method only the targets are read, so no other subject is touched.
    X, md = load_windows(
        epochs_dir,
        data_cfg,
        subjects=None if needs_source else exp.subjects,
        sessions=None if needs_source else list(exp.sessions),
        labels=labels,
        mirror=exp.mirror,
    )
    present = md[["subject", "session", "run"]].drop_duplicates().itertuples(index=False)
    if any(data_cfg.is_run_excluded(s, ss, f"{r:02d}") for s, ss, r in present):
        raise RuntimeError("The epoch cache holds an excluded run; rebuild it (make epochs).")

    ctx = RunContext(
        exp=exp,
        data_cfg=data_cfg,
        proto=proto,
        X=X,
        md=md,
        writer=ScoreWriter(out_path),
        done=completed_units(out_path),
        provenance=_provenance(epochs_dir),
        method_params={m: method_params(m, paths.configs) for m in exp.methods},
        base_hash=config_hash(data_cfg, proto, exp),
        processed=processed_dir or paths.processed,
    )
    log.info("%s: %d units already in %s", exp.name, len(ctx.done), out_path)
    try:
        if exp.protocol == "within_session":
            _run_within_session(ctx, n_jobs)
        else:
            if n_jobs > 1:
                log.warning("n_jobs applies to within-session experiments; running in one process")
            _run_calibration(ctx)
    finally:
        ctx.writer.flush()
    log.info("%s: %d new rows", exp.name, ctx.writer.n_written)
    return out_path


# Within-session protocols (RQ1) ------------------------------------------------------------


def within_splits(name: str, md: pd.DataFrame, proto: ProtocolConfig) -> tuple[list[Split], int]:
    """Splits of one subject-session under a named protocol, and its number of folds."""
    ws, seed = proto.within_session, proto.calibration.seed_base
    if name in ("cv_leakfree", "paper_replica"):
        folds = n_cv_folds(md, ws.cv_folds)
        fn = cv_leakfree_splits if name == "cv_leakfree" else paper_replica_splits
        return list(fn(md, folds, ws.cv_repeats, seed)), folds
    if name == "loro":
        splits = list(loro_splits(md))
        return splits, len(splits)
    return [chrono_split(md, ws.chrono_train_runs, ws.chrono_test_runs)], 1


def score_folds(
    X: np.ndarray,
    y: np.ndarray,
    md: pd.DataFrame,
    todo: list[tuple[int, Split]],
    method_name: str,
    params: dict,
    classes: list[int],
    protocol: str,
    seed: int,
) -> Iterator[tuple[int, dict, dict]]:
    """Fit and score one method on the listed folds of one subject-session.

    X, y and md are aligned (row i of md is X[i]); yields (fold, metrics, extra columns).
    """
    n_front = getattr(REGISTRY[method_name], "per_window_steps", 0)
    head = None
    if protocol == "paper_replica":
        # The one deliberate leak (protocol 4.1): every stage before the classifier sees all
        # windows of the session, test folds included. Its numbers only measure the leak.
        method = make_method(method_name, n_classes=len(classes), **params)
        if not hasattr(method, "build"):
            raise TypeError(f"{method_name} has no build(); paper_replica cannot split it")
        pipe = method.build()
        try:
            features, head = pipe[:-1].fit_transform(X, y), pipe[-1]
        except UndefinedCell as err:
            for fold, (tr, te) in todo:
                yield fold, None, dict(n_train=len(tr), n_test=len(te), reason=str(err))
            return
    elif n_front:
        # Leading steps without fitted parameters (FBCSP's filter bank) give each window the
        # same output in every fold, so they run once; the rest is fitted per fold as usual.
        pipe = make_method(method_name, n_classes=len(classes), **params).build()
        features, head = X, pipe[n_front:]
        for _, step in pipe.steps[:n_front]:
            features = step.transform(features)  # never fitted: nothing to learn from X
    for fold, (tr, te) in todo:
        assert_no_leakage(md.iloc[tr], md.iloc[te])
        t0 = time.perf_counter()
        try:
            if head is not None:
                model = clone(head).fit(features[tr], y[tr])
                proba = model.predict_proba(features[te])
            else:
                method = make_method(method_name, n_classes=len(classes), **params)
                method.fit(Batch(X[tr], y[tr], md.iloc[tr]), seed=seed)
                proba = method.predict_proba(X[te])
        except UndefinedCell as err:
            yield fold, None, dict(n_train=len(tr), n_test=len(te), reason=str(err))
            continue
        fit_seconds = time.perf_counter() - t0
        _check_proba(proba, len(te), classes, method_name)
        extra = dict(n_train=len(tr), n_test=len(te), fit_seconds=fit_seconds)
        yield fold, score(y[te], proba, classes), extra


def ersp_input(
    rows: pd.DataFrame,
    data_cfg: DataConfig,
    processed: Path,
    settings: dict,
    mirror: bool = False,
) -> tuple[pd.DataFrame, np.ndarray]:
    """The mu ERSP of cached imagery windows, the input of `csp_lda_replica` (protocol 5).

    The run files are cut again from the start of the baseline to the end of the window;
    a window whose wider span crosses a boundary is dropped by the cache's own rule.
    Returns the kept rows (index 0..n-1) and X: (n, 40, n_times) float32, dB.
    """
    if (rows.label == REST_ID).any():
        raise ValueError("The ERSP baseline is the second before an imagery cue; no REST windows")
    sfreq, window = data_cfg.signal.sfreq, data_cfg.window
    b0, b1 = settings["baseline_s"]
    keep, X_long = recut(rows, data_cfg, processed, b0, window.tmax, mirror=mirror)
    start = round((window.tmin - b0) * sfreq)
    X = ersp_db(
        X_long,
        sfreq,
        tuple(settings["band_hz"]),
        baseline=(0, round((b1 - b0) * sfreq)),
        keep=(start, start + data_cfg.n_times),
    )
    return rows[keep].reset_index(drop=True), X


@dataclass
class WithinJob:
    """The folds still to run for one subject, session and task."""

    task: str
    classes: list[int]
    subject: str
    session: str
    rows: pd.DataFrame  # the session's windows of the task's classes, cache order
    X: np.ndarray  # cached windows aligned with rows
    done: set  # unit keys of this subject, session and task already in the scores file


def _within_input(job: WithinJob, feature: str, params: dict, data_cfg, processed, mirror):
    if feature == "bandpower":
        return job.rows.reset_index(drop=True), job.X
    if feature == "ersp_mu":
        return ersp_input(job.rows, data_cfg, processed, params["ersp_mu"], mirror)
    raise ValueError(f"No input called {feature!r}")


def iter_within_job(
    job: WithinJob,
    exp: ExperimentConfig,
    proto: ProtocolConfig,
    data_cfg: DataConfig,
    params: dict[str, dict],
    processed: Path | None,
) -> Iterator[tuple[dict, dict, dict]]:
    """Every protocol and method of one job; yields (unit key, metrics, extra) per fold."""
    seeds = exp.seeds or [proto.calibration.seed_base]
    inputs: dict[tuple[str, str], tuple[pd.DataFrame, np.ndarray]] = {}
    splits: dict[tuple, tuple[list[Split], int]] = {}
    for proto_name in exp.within_protocols:
        for method_name in exp.methods:
            feature = feature_of(method_name)
            if feature not in exp.features:
                continue
            # Inputs depend on the method's settings (the ERSP band and baseline).
            input_id = (feature, json.dumps(params[method_name].get(feature), sort_keys=True))
            if input_id not in inputs:
                inputs[input_id] = _within_input(
                    job, feature, params[method_name], data_cfg, processed, exp.mirror
                )
            md, X = inputs[input_id]
            if (proto_name, input_id) not in splits:
                splits[(proto_name, input_id)] = within_splits(proto_name, md, proto)
            fold_splits, n_folds = splits[(proto_name, input_id)]
            y = md.label.to_numpy()
            for seed in seeds:
                key = dict(
                    experiment=exp.name,
                    protocol=proto_name,
                    scenario=None,
                    task=job.task,
                    method=method_name,
                    feature=feature,
                    subject=job.subject,
                    session=job.session,
                    k=None,
                    draw=str(seed) if exp.seeds else None,
                )
                todo = [
                    (fold, split)
                    for fold, split in enumerate(fold_splits)
                    if unit_key({**key, "fold": fold}) not in job.done
                ]
                if not todo:
                    continue
                for fold, metrics, extra in score_folds(
                    X, y, md, todo, method_name, params[method_name], job.classes, proto_name, seed
                ):
                    yield {**key, "fold": fold}, metrics, {**extra, "n_folds": n_folds}


def run_within_job(job: WithinJob, **kwargs) -> list[tuple[dict, dict, dict]]:
    return list(iter_within_job(job, **kwargs))


def _within_jobs(ctx: RunContext) -> Iterator[WithinJob]:
    exp, data_cfg, proto = ctx.exp, ctx.data_cfg, ctx.proto
    done = defaultdict(set)
    task_i, subject_i, session_i = (UNIT_KEYS.index(k) for k in ("task", "subject", "session"))
    for key in ctx.done:
        done[(key[task_i], key[subject_i], key[session_i])].add(key)
    for task in exp.tasks:
        classes = _class_ids(data_cfg, proto.tasks[task])
        for session in exp.sessions:
            for subject in exp.subjects:
                if session not in data_cfg.sessions_for(subject):
                    continue
                rows = ctx.md[
                    (ctx.md.subject == subject)
                    & (ctx.md.session == session)
                    & ctx.md.label.isin(classes)
                ]
                if rows.empty:
                    log.warning("%s %s %s: no windows", subject, session, task)
                    continue
                X = ctx.X[rows.index.to_numpy()]
                yield WithinJob(
                    task, classes, subject, session, rows, X, done[(task, subject, session)]
                )


def _run_within_session(ctx: RunContext, n_jobs: int = 1) -> None:
    kwargs = dict(
        exp=ctx.exp,
        proto=ctx.proto,
        data_cfg=ctx.data_cfg,
        params=ctx.method_params,
        processed=ctx.processed,
    )
    jobs = _within_jobs(ctx)
    if n_jobs == 1:
        # Rows go to the writer as each fold finishes, so a crash loses at most one buffer.
        for job in jobs:
            n = 0
            for key, metrics, extra in iter_within_job(job, **kwargs):
                ctx.write(key, metrics, **extra)
                n += 1
            log.info("%s %s %s: %d new rows", job.subject, job.session, job.task, n)
        return
    # Workers return whole jobs and only this process writes, so the scores file keeps a
    # single writer; a crash loses the jobs still running, which a resume redoes.
    work = partial(run_within_job, **kwargs)
    results = Parallel(n_jobs=n_jobs, return_as="generator_unordered")(
        delayed(work)(job) for job in jobs
    )
    for rows in results:
        for key, metrics, extra in rows:
            ctx.write(key, metrics, **extra)
        if rows:
            first = rows[0][0]
            log.info(
                "%s %s %s: %d new rows",
                first["subject"],
                first["session"],
                first["task"],
                len(rows),
            )


def _check_proba(proba: np.ndarray, n: int, classes: list[int], method_name: str) -> None:
    if proba.shape != (n, len(classes)):
        raise ValueError(f"{method_name} returned {proba.shape}, expected {(n, len(classes))}")


# Calibration protocol (RQ2, RQ3) -----------------------------------------------------------


def task_windows(drawn: pd.DataFrame, classes: list[int]) -> pd.DataFrame:
    """Training windows of a task from the drawn trials (protocol 4.2 table).

    Only trials whose imagery class belongs to the task count, and of those only the
    task's windows: T2 keeps every window, T3 the SF and REST windows of the SF trials.
    """
    mi_classes = [c for c in classes if c != 0]
    mi_label = drawn[drawn.label > 0].groupby("trial_uid").label.first()
    trials = mi_label[mi_label.isin(mi_classes)].index
    return drawn[drawn.trial_uid.isin(trials) & drawn.label.isin(classes)]


def ah_proxy_windows(pool: pd.DataFrame) -> pd.DataFrame:
    """AH and REST windows of every AH trial of the pool, whatever the task."""
    ah_trials = pool.trial_uid[pool.label == AH].unique()
    return pool[pool.trial_uid.isin(ah_trials) & pool.label.isin([0, AH])]


def map_ah_proxy(proba: np.ndarray, classes: list[int]) -> np.ndarray:
    """Spread the proxy's (REST, AH) columns over the task's classes.

    T3: its AH probability is scored as SF. T2: it never predicts SF (column of zeros).
    """
    out = np.zeros((len(proba), len(classes)))
    out[:, classes.index(0)] = proba[:, 0]
    out[:, classes.index(AH if AH in classes else SF)] = proba[:, 1]
    return out


def _draws_for(method_name: str, exp: ExperimentConfig, proto: ProtocolConfig) -> list[str]:
    cal = proto.calibration
    if exp.draws != "from_protocol":
        n = int(exp.draws)
    else:
        n = cal.draws_deep if getattr(REGISTRY[method_name], "deep", False) else cal.draws_classical
    draws = [str(cal.seed_base + i) for i in range(n)]
    return [*draws, "chrono"] if cal.chrono_draw else draws


def _seed(draw: str, proto: ProtocolConfig) -> int:
    return int(draw) if draw.isdigit() else proto.calibration.seed_base


def _run_calibration(ctx: RunContext) -> None:
    exp, data_cfg, proto = ctx.exp, ctx.data_cfg, ctx.proto
    cal, md = proto.calibration, ctx.md
    pool_runs = [int(r) for r in cal.pool_runs]
    test_runs = [int(r) for r in cal.test_runs]
    k_all = max(exp.k_grid)
    proxies: dict[tuple[str, str], object] = {}
    for task in exp.tasks:
        classes = _class_ids(data_cfg, proto.tasks[task])
        for session in exp.sessions:
            for target in exp.subjects:
                if session not in data_cfg.sessions_for(target):
                    continue  # e.g. sub-21/sub-22 pre: excluded
                log.info("%s %s %s", target, session, task)
                smask = (md.subject == target) & (md.session == session)
                # Three-class pool: one draw serves both tasks (protocol 4.2).
                pool = md[smask & md.run.isin(pool_runs)]
                in_test = smask & md.run.isin(test_runs)
                test = md[in_test & md.label.isin(classes)]
                sources = [
                    s
                    for s in data_cfg.subjects.ids
                    if data_cfg.split_group(s) != data_cfg.split_group(target)
                ]
                src = md[md.subject.isin(sources) & md.label.isin(classes)]
                for scen_name in exp.scenarios:
                    scen = cal.scenarios[scen_name]
                    full = _class_ids(data_cfg, scen.full_classes)
                    budget = _class_ids(data_cfg, scen.budget_classes)
                    # S2 T3 decoders also label the AH test windows, for the SF-vs-AH share.
                    ah_test = (
                        md[in_test & (md.label == AH)]
                        if AH in full and SF in classes and AH not in classes
                        else md.iloc[:0]
                    )
                    for method_name in exp.methods:
                        unit = _CalibUnit(
                            ctx, task, classes, session, target, scen_name, full, budget,
                            pool, test, ah_test, src, method_name, proxies,
                        )  # fmt: skip
                        for k in exp.k_grid:
                            proxy = method_name == AH_PROXY
                            one_draw = proxy or k == 0 or k == k_all
                            for draw in ["0"] if one_draw else _draws_for(method_name, exp, proto):
                                unit.run(k, draw)


@dataclass
class _CalibUnit:
    ctx: RunContext
    task: str
    classes: list[int]
    session: str
    target: str
    scenario: str
    full: list[int]
    budget: list[int]
    pool: pd.DataFrame
    test: pd.DataFrame
    ah_test: pd.DataFrame
    src: pd.DataFrame
    method_name: str
    proxies: dict

    def run(self, k: int, draw: str) -> None:
        ctx, name = self.ctx, self.method_name
        key = dict(
            experiment=ctx.exp.name,
            protocol="calib",
            scenario=self.scenario,
            task=self.task,
            method=name,
            feature=getattr(REGISTRY[name], "feature", "bandpower"),
            subject=self.target,
            session=self.session,
            k=k,
            draw=draw,
            fold=0,
        )
        if ctx.skip(key):
            return
        if self.test.empty:
            ctx.write(key, reason="no test windows")
            return
        cls = REGISTRY[name]
        uses_source = bool(getattr(cls, "uses_source", False))
        cd = draw_calibration_set(self.pool, self.full, self.budget, k, draw)
        k_used = json.dumps(cd.k_used)
        if name == AH_PROXY:
            train_md = ah_proxy_windows(self.pool)
            unl_md = train_md
        else:
            train_md = task_windows(self.pool.iloc[cd.labelled_idx], self.classes)
            unl_md = self.pool.iloc[cd.unlabelled_idx] if k == 0 else train_md
        src = self.src if uses_source else None
        assert_no_leakage(
            train_md,
            pd.concat([self.test, self.ah_test]),
            source=src,
            unlabelled=unl_md,
            target_subject=self.target,
            split_group=ctx.data_cfg.split_group,
        )
        n_info = dict(k_used=k_used, n_train=len(train_md), n_test=len(self.test))
        if 0 < k < getattr(cls, "min_trials_per_class", 1):
            ctx.write(key, reason="k below the method's declared minimum", **n_info)
            return
        if not uses_source and name != AH_PROXY and set(train_md.label) != set(self.classes):
            # From scratch cannot predict a class it has never seen (S1 k = 0, S2 k = 0).
            ctx.write(key, reason="no target data for every class", **n_info)
            return
        t0 = time.perf_counter()
        method = self._fitted(train_md, unl_md, src, draw)
        fit_seconds = time.perf_counter() - t0
        proba = self._predict(method, self.test)
        row = score(self.test.label.to_numpy(), proba, self.classes)
        sf_vs_ah = np.nan
        if len(self.ah_test):
            said = np.asarray(self.classes)[self._predict(method, self.ah_test).argmax(axis=1)]
            sf_vs_ah = float(np.mean(said == SF))
        ctx.write(key, row, sf_vs_ah=sf_vs_ah, fit_seconds=fit_seconds, **n_info)

    def _fitted(self, train_md, unl_md, src, draw):
        ctx, name = self.ctx, self.method_name
        if name == AH_PROXY:
            # Independent of k and task: fitted once per subject and session (protocol 4.2).
            cache_key = (self.target, self.session)
            if cache_key not in self.proxies:
                method = make_method(name, n_classes=2, **ctx.method_params[name])
                method.fit(ctx.batch(train_md), seed=ctx.proto.calibration.seed_base)
                self.proxies[cache_key] = method
            return self.proxies[cache_key]
        method = make_method(name, n_classes=len(self.classes), **ctx.method_params[name])
        return method.fit(
            ctx.batch(train_md),
            ctx.batch(src) if src is not None else None,
            ctx.batch(unl_md, labels=False),
            seed=_seed(draw, ctx.proto),
        )

    def _predict(self, method, rows: pd.DataFrame) -> np.ndarray:
        proba = method.predict_proba(self.ctx.X[rows.index.to_numpy()])
        if self.method_name == AH_PROXY:
            proba = map_ah_proxy(proba, self.classes)
        _check_proba(proba, len(rows), self.classes, self.method_name)
        return proba
