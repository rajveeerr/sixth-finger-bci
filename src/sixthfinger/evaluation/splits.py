"""Within-session and cross-subject splits defined in the evaluation protocol."""

from __future__ import annotations


def paper_replica_splits(*args, **kwargs):
    raise NotImplementedError("Implemented in phase P05.")


def cv_leakfree_splits(*args, **kwargs):
    raise NotImplementedError("Implemented in phase P05.")


def loro_splits(*args, **kwargs):
    raise NotImplementedError("Implemented in phase P05.")


def chrono_split(*args, **kwargs):
    raise NotImplementedError("Implemented in phase P05.")


def loso_groups(*args, **kwargs):
    raise NotImplementedError("Implemented in phase P05.")
