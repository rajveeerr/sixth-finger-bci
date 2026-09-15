from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from sixthfinger.data import audit
from sixthfinger.data.loading import list_processed_runs
from tests.conftest import synthetic_events, write_eeglab_mat


def test_audit_run_counts_the_fixture_events(mat_run):
    path, data = mat_run
    row = audit.audit_run(path)
    assert (row["n_rest"], row["n_ah"], row["n_sf"], row["n_boundary"]) == (4, 2, 2, 1)
    assert row["n_channels"] == data.shape[0]
    assert row["sfreq"] == 250.0
    assert row["cue_gap_median_s"] == np.float64(2142 / 250.0)
    assert row["flat_channels"] == 0


def test_event_flags_marks_count_degenerate_and_format():
    base = {
        "n_channels": 43, "sfreq": 250.0, "duration_s": 315.0,
        "n_rest": 20, "n_ah": 10, "n_sf": 10, "flat_channels": 0,
    }  # fmt: skip
    inv = pd.DataFrame(
        [
            base,
            {**base, "n_rest": 19},
            {**base, "n_ah": 3, "n_sf": 4},
            {**base, "flat_channels": 1},
        ]
    )
    flags = audit.event_flags(inv)
    assert list(flags.index) == [1, 2, 3]
    assert list(flags.flag) == ["count", "degenerate", "format"]


def test_segment_similarity_finds_a_shifted_copy_with_cuts():
    rng = np.random.default_rng(0)
    a = rng.standard_normal(250 * 200).astype(np.float32)
    # The copy starts 3 s later and has a 10 s stretch cut out, as EEGLAB edits do.
    b = np.concatenate([a[750:20_000], a[22_500:]])
    assert audit.segment_similarity(a, b) > 0.99
    assert audit.verdict(audit.segment_similarity(a, b)) == "same recording"


def test_segment_similarity_of_independent_noise_is_low():
    rng = np.random.default_rng(1)
    a = rng.standard_normal(250 * 200).astype(np.float32)
    b = rng.standard_normal(250 * 200).astype(np.float32)
    r = audit.segment_similarity(a, b)
    assert r < 0.2
    assert audit.verdict(r) == "independent"


def test_known_pairs_match_run_by_run(tmp_path: Path):
    root = tmp_path / "processed"
    for name in (
        "sub-02/post/sub-02_B_post_01_eeg.mat",
        "sub-02/follow/sub-02_B_follow_01_eeg.mat",
        "sub-02/follow/sub-02_B_follow_02_eeg.mat",
        "sub-21/pre/sub-21_T_pre_01_eeg.mat",
        "sub-22/pre/sub-22_T_pre_01_eeg.mat",
    ):
        write_eeglab_mat(root / name, events=synthetic_events(n_trials=2), n_times=2000)
    pairs = audit.known_pairs(list_processed_runs(root))
    assert pairs == [
        ("sub-02_B_post_01_eeg.mat", "sub-02_B_follow_01_eeg.mat"),
        ("sub-21_T_pre_01_eeg.mat", "sub-22_T_pre_01_eeg.mat"),
    ]


def test_pairwise_similarity_flags_a_copied_run(tmp_path: Path):
    root = tmp_path / "processed"
    n = 250 * 130
    original = write_eeglab_mat(root / "sub-01/pre/sub-01_B_pre_01_eeg.mat", n_times=n, seed=1)
    write_eeglab_mat(root / "sub-01/pre/sub-01_B_pre_02_eeg.mat", n_times=n, seed=2)
    copy_path = root / "sub-05/pre/sub-05_B_pre_01_eeg.mat"
    write_eeglab_mat(copy_path, n_times=n, seed=1)
    df = audit.pairwise_similarity(root)
    top = df.iloc[0]
    assert {top.run_a, top.run_b} == {"sub-01_B_pre_01_eeg.mat", "sub-05_B_pre_01_eeg.mat"}
    assert top.segment_median_r > 0.99
    assert len(df) == 1
    assert original.shape[1] == n
