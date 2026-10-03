"""Calibration-budget sampler for scenarios S1 and S2."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

REST_ID = 0


@dataclass
class CalibrationDraw:
    labelled_idx: np.ndarray  # rows of the pool used with labels
    unlabelled_idx: np.ndarray  # drawn trials (k > 0) or the pool's REST windows (k = 0)
    k_used: dict[str, int]  # per budget class, after capping


def mi_trials(pool: pd.DataFrame, label_id: int) -> pd.DataFrame:
    """Trials of the pool whose imagery window has this label, in time order."""
    rows = pool[pool.label == label_id]
    return rows.sort_values(["run", "trial_in_run"]).drop_duplicates("trial_uid")


def draw_calibration_set(
    pool: pd.DataFrame, full_ids: list[int], budget_ids: list[int], k: int, seed: int | str
) -> CalibrationDraw:
    """Pick trials for one (scenario, k, draw) and return row positions within `pool`.

    pool: the three-class windows of runs 01-02 of one subject-session, so that one draw
    serves every task. seed: an int for a random draw, or "chrono" for the first k
    trials in time order. The REST window of every chosen trial comes along with it.
    """
    chosen: list[str] = []
    k_used: dict[str, int] = {}
    for cid in full_ids:
        chosen += mi_trials(pool, cid).trial_uid.tolist()
    chrono = seed == "chrono"
    rng = None if chrono else np.random.default_rng(int(seed))
    for cid in budget_ids:
        trials = mi_trials(pool, cid).trial_uid.to_numpy()
        n = min(k, len(trials))
        k_used[str(cid)] = n
        if n == 0:
            continue
        pick = trials[:n] if chrono else rng.choice(trials, size=n, replace=False)
        chosen += list(pick)
    labelled = np.flatnonzero(pool.trial_uid.isin(chosen).to_numpy())
    # Unlabelled budget = labelled budget, so alignment sees nothing the labels did not;
    # k = 0 instead gets the declared set of protocol 4.2, every REST window of the pool.
    unlabelled = np.flatnonzero((pool.label == REST_ID).to_numpy()) if k == 0 else labelled
    return CalibrationDraw(labelled, unlabelled, k_used)
