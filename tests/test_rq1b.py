import importlib.util

import numpy as np
import pandas as pd
import pytest

from sixthfinger.config import load_protocol_config
from sixthfinger.paths import get_paths


@pytest.fixture(scope="module")
def rq1b():
    path = get_paths().root / "scripts" / "rq1b_public.py"
    spec = importlib.util.spec_from_file_location("rq1b_public", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _meta(runs: list[str], per_run: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "subject": 3,
            "session": "0train",
            "run": np.repeat(runs, per_run),
        }
    )


def test_runs_are_numbered_in_recording_order(rq1b):
    md, source = rq1b.session_metadata(_meta(["0", "1", "2", "3", "4", "5"], 24), "BNCI2014_001")
    assert source == "run" and md.run.tolist() == list(np.repeat(range(1, 7), 24))
    assert md.subject.iloc[0] == "sub-03" and md.trial_uid.is_unique


def test_a_session_without_four_runs_becomes_four_blocks(rq1b):
    md, source = rq1b.session_metadata(_meta(["0"], 202), "Cho2017")
    assert source == "blocks"
    assert md.run.value_counts().sort_index().tolist() == [51, 51, 50, 50]
    assert (np.diff(md.run.to_numpy()) >= 0).all()  # consecutive trials stay together


def test_chrono_trains_on_the_first_half_of_the_runs(rq1b):
    md, _ = rq1b.session_metadata(_meta(["0", "1", "2", "3", "4", "5"], 4), "BNCI2014_001")
    md["label"] = np.tile([1, 2], len(md) // 2)
    proto = load_protocol_config()
    [(tr, te)], n = rq1b.protocol_splits("chrono", md, proto)
    assert n == 1
    assert set(md.run.iloc[tr]) == {1, 2, 3} and set(md.run.iloc[te]) == {4, 5, 6}
    splits, n = rq1b.protocol_splits("loro", md, proto)
    assert n == 6 and all(len(set(md.run.iloc[te])) == 1 for _, te in splits)
    splits, n = rq1b.protocol_splits("cv_leakfree", md, proto)
    assert n == 10 and len(splits) == 100


def test_blocks_of_one_class_leave_chrono_unfittable(rq1b):
    # MOABB's Cho2017 stacks every left-hand trial before every right-hand one, so the
    # four blocks hold one class each: chrono trains on left hands only (OQ-P06-1).
    md, source = rq1b.session_metadata(_meta(["0"], 200), "Cho2017")
    md["label"] = np.repeat([1, 2], 100)
    proto = load_protocol_config()
    chrono, _ = rq1b.protocol_splits("chrono", md, proto)
    fit, one_class = rq1b.split_by_training_classes(list(enumerate(chrono)), md.label.to_numpy())
    assert source == "blocks" and not fit and len(one_class) == 1
    loro, _ = rq1b.protocol_splits("loro", md, proto)
    fit, one_class = rq1b.split_by_training_classes(list(enumerate(loro)), md.label.to_numpy())
    assert len(fit) == 4 and not one_class
    assert all(len(set(md.label.iloc[te])) == 1 for _, (_, te) in fit)
