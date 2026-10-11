"""Synthetic window metadata shaped like the cache, for the evaluation tests."""

from __future__ import annotations

import numpy as np
import pandas as pd


def session_md(
    subject: str = "sub-01",
    session: str = "pre",
    runs: tuple[int, ...] = (1, 2, 3, 4),
    drop_mi: tuple[tuple[int, int], ...] = ((2, 20),),
    drop_rest: tuple[tuple[int, int], ...] = (),
) -> pd.DataFrame:
    """20 trials per run, MI class alternating AH/SF; each trial has a REST and an MI window.

    drop_mi removes the MI window of (run, trial), the way a boundary drop does, so by
    default the SF class has only 19 trials in runs 01-02; drop_rest removes the REST window.
    """
    rows = []
    for run in runs:
        for trial in range(1, 21):
            uid = f"{subject}_ses-{session}_run-{run:02d}_trial-{trial:02d}"
            mi = 1 if trial % 2 else 2
            for label in (0, mi):
                if label and (run, trial) in drop_mi:
                    continue
                if not label and (run, trial) in drop_rest:
                    continue
                rows.append(
                    {
                        "subject": subject,
                        "session": session,
                        "run": run,
                        "trial_in_run": trial,
                        "trial_uid": uid,
                        "label": label,
                    }
                )
    return pd.DataFrame(rows)


def cohort_md(subjects: tuple[str, ...] = ("sub-01", "sub-21", "sub-22")) -> pd.DataFrame:
    return pd.concat([session_md(s) for s in subjects], ignore_index=True)


def split_group(subject: str) -> str:
    return "sub-21+sub-22" if subject in ("sub-21", "sub-22") else subject


def windows_for(md: pd.DataFrame, n_channels: int = 4, n_times: int = 50, seed: int = 0):
    rng = np.random.default_rng(seed)
    return rng.standard_normal((len(md), n_channels, n_times)).astype(np.float32)
