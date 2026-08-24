import numpy as np
import pytest

from sixthfinger.data.channels import CHANNELS_40
from sixthfinger.data.loading import (
    BOUNDARY,
    list_processed_runs,
    load_processed_run,
    parse_run_filename,
    read_eeglab_mat,
    record_to_raw,
)
from tests.conftest import FILE_CHANNELS


def test_read_mat_events_are_zero_based(mat_run):
    path, data = mat_run
    rec = read_eeglab_mat(path)
    assert rec.data_uv.shape == data.shape
    assert rec.ch_names == list(FILE_CHANNELS)
    assert rec.event_codes[:3] == ["boundary", "1", rec.event_codes[2]]
    assert rec.event_samples[0] == 0
    assert rec.event_samples[1] == 750
    assert rec.event_samples[2] - rec.event_samples[1] == 2142


def test_raw_has_40_channels_in_volts(mat_run):
    path, data = mat_run
    raw, info = load_processed_run(path)
    assert raw.ch_names == list(CHANNELS_40)
    c3_file = FILE_CHANNELS.index("C3")
    np.testing.assert_allclose(raw.get_data(picks="C3")[0], data[c3_file] * 1e-6, rtol=1e-6)
    assert info.subject == "sub-03" and info.session == "pre" and info.run == "01"


def test_annotations(mat_run):
    path, _ = mat_run
    raw, _ = load_processed_run(path)
    desc = list(raw.annotations.description)
    assert desc[0] == BOUNDARY
    assert desc.count("1") == 4
    assert desc.count("2") + desc.count("3") == 4


def test_missing_channel_raises(mat_run):
    path, _ = mat_run
    rec = read_eeglab_mat(path)
    with pytest.raises(ValueError, match="missing"):
        record_to_raw(rec, channels=("C3", "Oz"))


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("sub-01_B_pre_01_eeg.mat", ("sub-01", "B", "pre", "01")),
        ("sub-22_T_follow_04_eeg.mat", ("sub-22", "T", "follow", "04")),
        ("sub-02_B_post_03_original.set", ("sub-02", "B", "post", "03")),
    ],
)
def test_parse_filename(tmp_path, name, expected):
    info = parse_run_filename(tmp_path / name)
    assert (info.subject, info.group, info.session, info.run) == expected


def test_parse_filename_rejects_other_names(tmp_path):
    with pytest.raises(ValueError):
        parse_run_filename(tmp_path / "Post_Add all.mat")


def test_list_runs_sorted_by_session_order(processed_tree):
    runs = list_processed_runs(processed_tree)
    assert len(runs) == 8
    assert [r.session for r in runs[:4]] == ["pre", "pre", "post", "post"]
