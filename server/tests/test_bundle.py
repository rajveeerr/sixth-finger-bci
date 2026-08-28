import json
import shutil

import numpy as np
import pytest

from app.bundle import Bundle, PreprocessOp, apply_preprocessing
from app.synthetic import make_trial


def test_manifest_matches_files(bundle):
    m = bundle.manifest
    assert m.synthetic is True
    assert len(m.channels) == 40
    assert bundle.n_trials == 4
    assert [c.command for c in m.classes] == ["IDLE", "HAND_GRASP", "SIXTH_FINGER_FLEX"]


def test_int16_round_trip_is_within_one_step(bundle):
    original, cue_s = make_trial(np.random.default_rng(7), label=1)
    decoded = bundle.trial_data(0)
    assert decoded.shape == original.shape
    assert bundle.manifest.trials[0].cue_onset_s == cue_s
    assert np.abs(decoded - original).max() <= bundle.manifest.encoding.scale_uv / 2 + 1e-6


def test_tampered_trials_file_is_rejected(bundle_dir, tmp_path):
    copy = tmp_path / "bundle"
    shutil.copytree(bundle_dir, copy)
    with (copy / "trials.bin").open("r+b") as handle:
        handle.write(b"\x00\x01")
    with pytest.raises(ValueError, match="checksum"):
        Bundle(copy)


def test_display_channels_must_exist(bundle_dir, tmp_path):
    copy = tmp_path / "bundle"
    shutil.copytree(bundle_dir, copy)
    manifest = json.loads((copy / "manifest.json").read_text())
    manifest["display_channels"].append("Oz")
    (copy / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="display channels"):
        Bundle(copy)


def test_preprocessing_ops_apply_in_order():
    x = np.arange(6, dtype=np.float32).reshape(2, 3)
    ops = [
        PreprocessOp(op="scale", factor=2.0),
        PreprocessOp(op="spatial_filter", matrix=[[0.0, 1.0], [1.0, 0.0]]),
        PreprocessOp(op="channel_standardize", mean=[1.0, 0.0], std=[2.0, 1.0]),
    ]
    out = apply_preprocessing(x, ops)
    expected = np.array([[2.5, 3.5, 4.5], [0.0, 2.0, 4.0]], dtype=np.float32)
    np.testing.assert_allclose(out, expected)
    assert x[0, 1] == 1.0
