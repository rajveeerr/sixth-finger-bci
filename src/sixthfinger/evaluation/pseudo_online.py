"""Pseudo-online (self-paced) replay through the demo's command gate (protocol §6b, P09 Study 4).

A test run is replayed as one continuous signal: a 4 s window ending every 0.5 s is classified,
windows that overlap a `boundary` event are skipped (the gate keeps its state), and the class
probabilities pass through the server's own `CommandGate`, loaded from `server/app/gate.py`
rather than copied, so what is measured is the demo's behaviour. Nothing here is fitted on the
replayed runs.
"""

from __future__ import annotations

import importlib.util
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from sixthfinger.paths import find_root

REST, AH, SF = 0, 1, 2
COMMANDS = {AH: "HAND_GRASP", SF: "SIXTH_FINGER_FLEX"}
STRIDE_S, REST_S, IMAGERY_S, TRIAL_S = 0.5, 7.0, 6.0, 14.0
PERIOD_OF_CODE = {"1": ("rest", REST_S), "2": ("AH", IMAGERY_S), "3": ("SF", IMAGERY_S)}


def load_gate_class() -> type:
    """The server's CommandGate class itself (protocol §6b: import it, never re-implement it)."""
    path = find_root() / "server" / "app" / "gate.py"
    spec = importlib.util.spec_from_file_location("sixthfinger_server_gate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.CommandGate


def window_ends(n_times: int, n_window: int, stride: int, boundaries: np.ndarray) -> np.ndarray:
    """End samples (exclusive) of the windows [end - n_window, end) every `stride` samples,
    without those a boundary splits (a cut just before b splits [s, e) when s < b < e)."""
    ends = np.arange(n_window, n_times + 1, stride)
    b = np.asarray(boundaries)
    if not b.size:
        return ends
    starts = ends - n_window
    split = ((b[None, :] > starts[:, None]) & (b[None, :] < ends[:, None])).any(axis=1)
    return ends[~split]


def periods(codes: list[str], samples: np.ndarray, sfreq: float, n_times: int) -> pd.DataFrame:
    """Scored periods of a run: 7 s of rest after code 1, 6 s of imagery after codes 2 and 3."""
    rows = []
    for code, start in zip(codes, samples, strict=True):
        if code in PERIOD_OF_CODE:
            kind, seconds = PERIOD_OF_CODE[code]
            stop = min(int(start) + round(seconds * sfreq), n_times)
            rows.append(dict(kind=kind, start=int(start), stop=stop))
    return pd.DataFrame(rows, columns=["kind", "start", "stop"])


def replay(proba: np.ndarray, gate_cls: type) -> np.ndarray:
    """The gate's output after each window of one run, the gate reset at the run's start."""
    gate = gate_cls(n_classes=proba.shape[1], rest_index=REST)
    gate.reset()
    return np.array([gate.update(p) for p in proba], dtype=int)


def activations(active: np.ndarray, ends: np.ndarray) -> pd.DataFrame:
    """Onsets of a change of the gate's output from IDLE to a command (protocol §6b)."""
    prev = np.r_[REST, active[:-1]]
    onset = (prev == REST) & (active != REST)
    switches = int(((prev != REST) & (active != REST) & (active != prev)).sum())
    out = pd.DataFrame({"sample": ends[onset], "command": active[onset]})
    out.attrs["command_switches"] = switches  # command to command, not an activation
    return out


def replay_run(
    predict_proba,
    data: np.ndarray,
    codes: list[str],
    samples: np.ndarray,
    sfreq: float,
    n_window: int,
    gate_cls: type,
):
    """Replay one continuous run (channels, samples) through the gate.

    `predict_proba` takes windows (n, channels, n_window) and returns probabilities in class
    order [REST, AH, SF], the order of the gate's indices. Returns the run's RunReplay and its
    timeline (window end times, probabilities, gate output).
    """
    codes = list(codes)
    boundaries = np.asarray(samples)[np.array(codes) == "boundary"]
    ends = window_ends(data.shape[1], n_window, round(STRIDE_S * sfreq), boundaries)
    chunks = np.array_split(ends, max(1, len(ends) // 256))
    proba = np.concatenate(
        [predict_proba(np.stack([data[:, e - n_window : e] for e in c])) for c in chunks]
    )
    if proba.shape != (len(ends), 3):
        raise ValueError(f"probabilities of shape {proba.shape}, expected ({len(ends)}, 3)")
    active = replay(proba, gate_cls)
    per = periods(codes, samples, sfreq, data.shape[1])
    timeline = pd.DataFrame({"t": ends / sfreq, "p_rest": proba[:, REST], "p_ah": proba[:, AH],
                             "p_sf": proba[:, SF], "active": active})  # fmt: skip
    return RunReplay(per, activations(active, ends), sfreq), timeline


def replayed_runs(experiment_test_runs, experiment_pool_runs) -> list[int]:
    """The runs to replay: the experiment's test runs, which must not hold fitted data."""
    test, pool = {int(r) for r in experiment_test_runs}, {int(r) for r in experiment_pool_runs}
    if test & pool:
        raise ValueError(f"replayed runs {sorted(test)} overlap the fitted pool {sorted(pool)}")
    return sorted(test)


@dataclass
class RunReplay:
    """One replayed run: its periods and the gate's activations, in samples of the run."""

    periods: pd.DataFrame
    activations: pd.DataFrame
    sfreq: float


def _in(sample: int, start: np.ndarray, stop: np.ndarray) -> np.ndarray:
    return (start <= sample) & (sample < stop)


def itr_bits_per_minute(p: float, n: int = 2, trial_s: float = TRIAL_S) -> float:
    """Wolpaw ITR, one selection per trial; P at or below chance gives 0 (protocol §6b)."""
    if p <= 1 / n:
        return 0.0
    bits = math.log2(n) + p * math.log2(p)
    if p < 1:
        bits += (1 - p) * math.log2((1 - p) / (n - 1))
    return bits * 60 / trial_s


def subject_metrics(runs: list[RunReplay]) -> dict:
    """Protocol §6b metrics over the replayed runs of one subject and method."""
    n = dict(rest=0, AH=0, SF=0)
    detected = dict(AH=0, SF=0)
    latency = dict(AH=[], SF=[])
    ah_as_sf = rest_quiet = false = switches = 0
    rest_s = 0.0
    for run in runs:
        acts, sf_ = run.activations, run.sfreq
        switches += acts.attrs.get("command_switches", 0)
        for p in run.periods.itertuples():
            inside = acts[_in(acts["sample"].to_numpy(), p.start, p.stop)]
            n[p.kind] += 1
            if p.kind == "rest":
                rest_s += (p.stop - p.start) / sf_
                false += len(inside)
                rest_quiet += inside.empty
                continue
            own = AH if p.kind == "AH" else SF
            hits = inside[inside.command == own]
            if len(hits):
                detected[p.kind] += 1
                latency[p.kind].append((hits["sample"].iloc[0] - p.start) / sf_)
            if p.kind == "AH" and (inside.command == SF).any():
                ah_as_sf += 1
    p_correct = (detected["SF"] + rest_quiet) / max(n["SF"] + n["rest"], 1)
    rate = lambda a, b: a / b if b else np.nan  # noqa: E731
    return {
        "n_sf_periods": n["SF"],
        "n_ah_periods": n["AH"],
        "n_rest_periods": n["rest"],
        "sf_detection_rate": rate(detected["SF"], n["SF"]),
        "ah_detection_rate": rate(detected["AH"], n["AH"]),
        "ah_as_sf_rate": rate(ah_as_sf, n["AH"]),  # added after the P08 results
        "rest_minutes": rest_s / 60,
        "false_activations": false,
        "false_per_minute": rate(false, rest_s / 60),
        "sf_latency_s": float(np.median(latency["SF"])) if latency["SF"] else np.nan,
        "ah_latency_s": float(np.median(latency["AH"])) if latency["AH"] else np.nan,
        "itr_p_correct": p_correct,
        "itr_bits_per_min": itr_bits_per_minute(p_correct),
        "command_switches": switches,
    }


def any_imagery(proba: np.ndarray) -> np.ndarray:
    """The one-switch view (added after the P08 results): P(rest) against P(AH) + P(SF)."""
    return np.column_stack([proba[:, REST], proba[:, AH] + proba[:, SF]])


def switch_metrics(runs: list[RunReplay]) -> dict:
    """One-switch replay: an imagery period (AH or SF) is detected by any activation inside it;
    false activations as in protocol §6b."""
    n_img = hit = false = 0
    rest_s, latency = 0.0, []
    for run in runs:
        acts, sf_ = run.activations, run.sfreq
        for p in run.periods.itertuples():
            inside = acts[_in(acts["sample"].to_numpy(), p.start, p.stop)]
            if p.kind == "rest":
                rest_s += (p.stop - p.start) / sf_
                false += len(inside)
            else:
                n_img += 1
                if len(inside):
                    hit += 1
                    latency.append((inside["sample"].iloc[0] - p.start) / sf_)
    return {
        "n_imagery_periods": n_img,
        "imagery_detection_rate": hit / n_img if n_img else np.nan,
        "false_per_minute": false / (rest_s / 60) if rest_s else np.nan,
        "latency_s": float(np.median(latency)) if latency else np.nan,
    }
