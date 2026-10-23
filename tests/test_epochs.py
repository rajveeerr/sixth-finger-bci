from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from sixthfinger.config import RunExclusion, load_data_config
from sixthfinger.data import epochs
from sixthfinger.data.channels import CHANNELS_40
from sixthfinger.paths import get_paths
from tests.conftest import FILE_CHANNELS, write_eeglab_mat


@pytest.fixture
def cfg():
    return load_data_config()


def _write_session(root: Path, subject: str, group: str, session: str, runs=("01", "02"), seed=0):
    for run in runs:
        name = f"{subject}_{group}_{session}_{run}_eeg.mat"
        write_eeglab_mat(root / subject / session / name, seed=seed + int(run))


def _write_subject(root: Path, subject: str, group: str, runs=("01", "02")):
    for seed, session in enumerate(("pre", "post", "follow")):
        _write_session(root, subject, group, session, runs, seed=10 * seed)


@pytest.fixture
def full_tree(tmp_path) -> Path:
    root = tmp_path / "processed"
    _write_subject(root, "sub-01", "B")
    _write_subject(root, "sub-07", "T")
    return root


def test_windows_have_config_length_channels_and_volts(mat_run, cfg):
    path, data_uv = mat_run
    rows, dropped = epochs.cut_run(path, cfg)
    assert not dropped
    assert len(rows) == 8
    x, label, trial, t0 = rows[0]
    assert x.shape == (40, cfg.n_times) == (40, 1000)
    assert list(cfg.channels.keep) == list(CHANNELS_40)
    # First event after the boundary is a rest marker at latency 751 (sample 750).
    start = 750 + round(cfg.window.tmin * 250)
    c3 = FILE_CHANNELS.index("C3")
    np.testing.assert_allclose(x[CHANNELS_40.index("C3")], data_uv[c3, start : start + 1000] * 1e-6)
    assert label == 0 and trial == 1 and t0 == start / 250


def test_boundary_and_end_drops(tmp_path, cfg):
    events = [("1", 1001), ("boundary", 1400), ("2", 3001), ("1", 6001)]
    path = tmp_path / "processed/sub-01/pre/sub-01_B_pre_01_eeg.mat"
    write_eeglab_mat(path, events=events, n_times=6800)
    rows, dropped = epochs.cut_run(path, cfg)
    assert [r[1] for r in rows] == [1]
    assert sorted(d["reason"] for d in dropped) == ["boundary_inside", "past_end"]


def test_assign_trials_never_puts_two_cues_in_one_trial():
    assert epochs.assign_trials(["boundary", "3", "1", "2", "1", "1", "3"]) == [0, 1, 2, 2, 3, 4, 4]


def test_rest_and_cue_of_one_trial_share_a_uid(processed_tree, cfg):
    sw = epochs.build_session("sub-01", "pre", cfg, processed_tree)
    by_uid = pd.Series(sw.y).groupby(sw.trial_uid).apply(sorted)
    assert len(by_uid) == 8
    assert all(labels[0] == 0 and len(labels) == 2 for labels in by_uid)


def test_excluded_sessions_and_runs_are_skipped(tmp_path, cfg):
    root = tmp_path / "processed"
    _write_subject(root, "sub-02", "B")
    runs = [RunExclusion(subject="sub-02", session="post", run="02", reason="test")]
    cfg = cfg.model_copy(update={"exclusions": cfg.exclusions.model_copy(update={"runs": runs})})
    md = epochs.build_all(cfg, root, tmp_path / "epochs", subjects=["sub-02"])
    assert set(md.session) == {"pre", "post"}
    assert set(md[md.session == "post"].run) == {1}
    manifest = json.loads((tmp_path / "epochs/manifest.json").read_text())
    assert "sub-02/post/02" in manifest["excluded_runs"]


def test_load_refuses_a_cache_built_with_other_settings(full_tree, tmp_path, cfg):
    out = tmp_path / "epochs"
    epochs.build_all(cfg, full_tree, out, subjects=["sub-01"])
    other = cfg.model_copy(update={"window": cfg.window.model_copy(update={"tmin": 0.5})})
    with pytest.raises(RuntimeError, match="window"):
        epochs.load_windows(out, other)
    X, md = epochs.load_windows(out, cfg)
    assert X.shape == (len(md), 40, 1000)
    assert X.dtype == np.float32


def test_mirror_swaps_c3_c4_for_left_hemiplegic_only(tmp_path, cfg):
    root = tmp_path / "processed"
    _write_subject(root, "sub-03", "B", runs=("01",))  # left hemiplegia
    out = tmp_path / "epochs"
    epochs.build_all(cfg, root, out, subjects=["sub-03"])
    X, _ = epochs.load_windows(out, cfg)
    Xm, _ = epochs.load_windows(out, cfg, mirror=True)
    c3, c4, cz = (CHANNELS_40.index(c) for c in ("C3", "C4", "Cz"))
    np.testing.assert_array_equal(Xm[:, c3], X[:, c4])
    np.testing.assert_array_equal(Xm[:, c4], X[:, c3])
    np.testing.assert_array_equal(Xm[:, cz], X[:, cz])


def test_subset_rebuild_keeps_other_subjects(full_tree, tmp_path, cfg):
    out = tmp_path / "epochs"
    epochs.build_all(cfg, full_tree, out, subjects=["sub-01", "sub-07"])
    before = json.loads((out / "manifest.json").read_text())["files"]
    epochs.build_all(cfg, full_tree, out, subjects=["sub-01"])
    md = pd.read_parquet(out / "metadata.parquet")
    after = json.loads((out / "manifest.json").read_text())["files"]
    assert set(md.subject) == {"sub-01", "sub-07"}
    assert after["sub-07_ses-pre.npz"] == before["sub-07_ses-pre.npz"]


@pytest.mark.real_data
def test_real_cache_dev_subject_counts():
    paths, cfg = get_paths(), load_data_config()
    X, md = epochs.load_windows(paths.epochs, cfg, subjects=["sub-01"], sessions=["pre"])
    counts = md.label_name.value_counts().to_dict()
    assert counts == {"rest": 80, "affected_hand": 40, "sixth_finger": 39}
    assert md.trial_uid.nunique() == 80
    assert X.shape == (159, 40, 1000)
    mi = md[md.label != 0]
    assert not mi.trial_uid.duplicated().any()


def test_boundaries_between_samples_split_only_the_windows_they_fall_in(tmp_path, cfg):
    # Cue at sample 1000: its window is [1250, 2250). EEGLAB puts cuts at n + 0.5.
    # 1250.5 (1-based) is the cut between samples 1249 and 1250, just before the window.
    # 2250.5 is between 2249 and 2250, just after it. 1251.5 is inside.
    def drops(lat):
        events = [("2", 1001), ("boundary", lat)]
        path = tmp_path / f"processed/sub-01/pre/sub-01_B_pre_01_{int(lat)}.mat"
        write_eeglab_mat(path, events=events, n_times=3000)
        path = path.rename(path.with_name("sub-01_B_pre_01_eeg.mat"))
        _, dropped = epochs.cut_run(path, cfg)
        return [d["reason"] for d in dropped]

    assert drops(1250.5) == []
    assert drops(2250.5) == []
    assert drops(1251.5) == ["boundary_inside"]
    assert drops(2249.5) == ["boundary_inside"]


def test_build_all_refuses_an_empty_subject_list(processed_tree, tmp_path, cfg):
    with pytest.raises(ValueError, match="non-empty"):
        epochs.build_all(cfg, processed_tree, tmp_path / "epochs", subjects=[])


def test_load_refuses_files_that_disagree_with_the_metadata(full_tree, tmp_path, cfg):
    out = tmp_path / "epochs"
    epochs.build_all(cfg, full_tree, out, subjects=["sub-01"])
    name = "sub-01_ses-pre.npz"
    with np.load(out / name) as npz:
        arrays = {k: npz[k][:-1] for k in npz.files}
    np.savez(out / name, **arrays)
    with pytest.raises(RuntimeError, match="metadata"):
        epochs.load_windows(out, cfg)


def test_recut_reproduces_the_cache_and_widens_it(full_tree, tmp_path, cfg):
    out = tmp_path / "epochs"
    epochs.build_all(cfg, full_tree, out, subjects=["sub-01"])
    X, md = epochs.load_windows(out, cfg, subjects=["sub-01"])
    keep, same = epochs.recut(md, cfg, full_tree, cfg.window.tmin, cfg.window.tmax)
    assert keep.all() and np.array_equal(same, X)
    keep, wide = epochs.recut(md, cfg, full_tree, -1.0, cfg.window.tmax)
    assert keep.all() and wide.shape == (len(md), 40, 1500)
    assert np.array_equal(wide[..., 500:], X)


def test_recut_drops_a_window_whose_wider_span_crosses_a_boundary(tmp_path, cfg):
    # The AH cue at sample 2000 keeps its cached window [2250, 3250), but the cut at
    # 1899.5 falls in the second before the cue, inside the wider [1750, 3250).
    events = [("1", 601), ("boundary", 1900.5), ("2", 2001), ("1", 4001), ("3", 5501)]
    root = tmp_path / "processed"
    write_eeglab_mat(root / "sub-01/pre/sub-01_B_pre_01_eeg.mat", events=events, n_times=8000)
    rows = pd.DataFrame(
        {
            "subject": "sub-01",
            "session": "pre",
            "run": 1,
            "trial_in_run": [1, 1, 2, 2],
            "label": [0, 1, 0, 2],
        }
    )
    keep, X = epochs.recut(rows, cfg, root, cfg.window.tmin, cfg.window.tmax)
    assert keep.all()
    keep, X = epochs.recut(rows, cfg, root, -1.0, cfg.window.tmax)
    assert keep.tolist() == [True, False, True, True] and X.shape == (3, 40, 1500)


def test_trial_counts_name_each_trial_by_the_windows_it_kept():
    md = pd.DataFrame(
        {
            "subject": ["sub-01"] * 5,
            "session": ["pre"] * 5,
            "run": [1, 1, 1, 1, 2],
            "trial_in_run": [1, 1, 2, 3, 1],
            "label_name": ["rest", "sixth_finger", "rest", "affected_hand", "rest"],
        }
    )
    row = epochs.trial_counts(md).loc[("sub-01", "pre")]
    assert row.trials == 4
    assert (row.rest_and_sixth_finger, row.rest_only, row.affected_hand_only) == (1, 2, 1)
    assert row.rest_and_affected_hand == 0
    with pytest.raises(ValueError, match="other windows"):
        epochs.trial_counts(md.assign(label_name="rest"))
