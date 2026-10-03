"""Within-session and cross-subject splits defined in the evaluation protocol."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import numpy as np
import pandas as pd
from sklearn.model_selection import LeaveOneGroupOut, RepeatedStratifiedKFold

Split = tuple[np.ndarray, np.ndarray]


def _trial_table(md: pd.DataFrame) -> pd.DataFrame:
    # One row per trial; the MI label (always larger than REST's 0) stratifies the folds.
    return md.groupby("trial_uid", sort=True).agg(strat=("label", "max"), run=("run", "first"))


def n_cv_folds(md: pd.DataFrame, folds: int) -> int:
    """Folds actually usable: stratified CV needs every imagery class in every fold."""
    counts = _trial_table(md).strat.value_counts()
    # A trial that lost its MI window to a boundary keeps only REST; such strays are too few
    # to set the fold count and sklearn simply spreads them over the folds.
    mi = counts[counts.index > 0]
    return int(min(folds, (mi if len(mi) else counts).min()))


def cv_leakfree_splits(md: pd.DataFrame, folds: int, repeats: int, seed: int) -> Iterator[Split]:
    """Rows of one subject-session, folded by trial so a trial's windows stay together."""
    trials = _trial_table(md)
    cv = RepeatedStratifiedKFold(n_splits=folds, n_repeats=repeats, random_state=seed)
    uid = md.trial_uid.to_numpy()
    for _, te in cv.split(trials.index, trials.strat):
        is_test = np.isin(uid, trials.index[te])
        yield np.flatnonzero(~is_test), np.flatnonzero(is_test)


def paper_replica_splits(md: pd.DataFrame, folds: int, repeats: int, seed: int) -> Iterator[Split]:
    # Same folds as cv_leakfree; the leak is in what the runner fits on all windows first.
    yield from cv_leakfree_splits(md, folds, repeats, seed)


def loro_splits(md: pd.DataFrame) -> Iterator[Split]:
    runs = md.run.to_numpy()
    yield from LeaveOneGroupOut().split(np.zeros(len(md)), groups=runs)


def chrono_split(md: pd.DataFrame, train_runs: list[str], test_runs: list[str]) -> Split:
    runs = md.run.astype(int).to_numpy()
    tr = np.isin(runs, [int(r) for r in train_runs])
    te = np.isin(runs, [int(r) for r in test_runs])
    return np.flatnonzero(tr), np.flatnonzero(te)


def loso_groups(subjects: list[str], split_group: Callable[[str], str]) -> dict[str, list[str]]:
    """Source subjects allowed for each target: everyone outside the target's split group."""
    return {t: [s for s in subjects if split_group(s) != split_group(t)] for t in subjects}
