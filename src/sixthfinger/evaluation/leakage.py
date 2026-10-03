"""Assertions that a train/test split respects the protocol."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd


class LeakageError(AssertionError):
    pass


def assert_no_leakage(
    train: pd.DataFrame,
    test: pd.DataFrame,
    *,
    source: pd.DataFrame | None = None,
    unlabelled: pd.DataFrame | None = None,
    target_subject: str | None = None,
    split_group: Callable[[str], str] | None = None,
) -> None:
    """Raise LeakageError if any rule of protocol section 9 is broken.

    Checked by trial UID, so a REST window cannot sit on the other side of its MI window.
    """
    test_uids = set(test.trial_uid)
    if shared := test_uids & set(train.trial_uid):
        raise LeakageError(f"{len(shared)} test trials in training, e.g. {sorted(shared)[:3]}")
    if unlabelled is not None and (shared := test_uids & set(unlabelled.trial_uid)):
        raise LeakageError(f"{len(shared)} test trials in the unlabelled set")
    if source is not None and len(source):
        if shared := test_uids & set(source.trial_uid):
            raise LeakageError(f"{len(shared)} test trials in source data")
        if target_subject is not None:
            group = split_group(target_subject) if split_group else target_subject
            bad = {
                s
                for s in source.subject.unique()
                if s == target_subject or (split_group and split_group(s) == group)
            }
            if bad:
                raise LeakageError(
                    f"source contains the target or its linked subject: {sorted(bad)}"
                )
