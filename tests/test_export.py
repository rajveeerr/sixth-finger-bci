import json

import numpy as np
import pytest
import torch
from braindecode.models import EEGNet

from sixthfinger.export import demo_bundle as db
from sixthfinger.export.onnx_export import export_onnx, onnx_probabilities, strip_parametrizations
from sixthfinger.paths import get_paths


def test_export_keeps_the_network_and_outputs_probabilities(tmp_path):
    torch.manual_seed(0)
    net = EEGNet(n_chans=8, n_outputs=3, n_times=256).eval()
    real = (5 * np.random.default_rng(1).standard_normal((6, 8, 256))).astype(np.float32)
    info = export_onnx(net, tmp_path / "m.onnx", 8, 256, real=real)
    assert info["max_abs_diff_random"] < 1e-5 and info["max_abs_diff_real"] < 1e-5
    p = onnx_probabilities(tmp_path / "m.onnx", real)
    np.testing.assert_allclose(p.sum(axis=1), 1, atol=1e-5)
    with torch.no_grad():  # the original network still works after the export of its copy
        np.testing.assert_allclose(p, torch.softmax(net(torch.from_numpy(real)), -1), atol=1e-5)
    assert torch.nn.utils.parametrize.is_parametrized(net.conv_spatial)


def test_parametrisations_are_baked_in():
    net = EEGNet(n_chans=8, n_outputs=3, n_times=256)
    plain = strip_parametrizations(net)
    assert not any(torch.nn.utils.parametrize.is_parametrized(m) for m in plain.modules())


def test_a_trial_is_whole_only_without_a_cut_inside():
    sf = 250
    codes = np.array(["1", "3", "1", "2", "boundary", "1", "3", "2"])
    samples = np.array([0, 2100, 4000, 6100, 6500, 8000, 10100, 13000])
    spans = db.trial_spans(codes, samples, sf, n_times=11000)
    by_trial = {s["trial"]: s for s in spans}
    assert by_trial[1]["whole"] and by_trial[1]["stop"] == 2100 + 6 * sf
    assert not by_trial[2]["whole"]  # the cut at 6500 is inside [4000, 7600)
    assert not by_trial[3]["whole"]  # cue + 6 s runs past the end of the run
    assert 4 not in by_trial  # a cue without its rest marker is no trial here


def test_encoding_round_trips_through_the_servers_bundle(tmp_path):
    rng = np.random.default_rng(0)
    trials = [dict(uid=f"t{i}", label=1 + i % 2, start=0, cue=2100, sfreq=250.0,
                   data_uv=(20 * rng.standard_normal((40, 3600))).astype(np.float32))
              for i in range(3)]  # fmt: skip
    blob, table, clipped = db.encode(trials)
    assert clipped == 0 and len(blob) == 3 * 40 * 3600 * 2
    (tmp_path / "trials.bin").write_bytes(blob)
    bundle_mod = db.server_module("bundle")
    raw = np.frombuffer(blob, dtype="<i2")
    first = raw[: 40 * 3600].reshape(40, 3600).astype(np.float32) * db.SCALE_UV
    assert np.abs(first - trials[0]["data_uv"]).max() <= db.SCALE_UV / 2 + 1e-5
    assert table[1]["offset_bytes"] == 40 * 3600 * 2 and table[1]["cue_onset_s"] == 8.4
    assert bundle_mod.SCHEMA_VERSION == 1


@pytest.mark.real_data
def test_the_real_bundle_matches_its_predictions_and_summary():
    root = get_paths().root
    bundle_mod, inference = db.server_module("bundle"), db.server_module("inference")
    bundle = bundle_mod.Bundle(root / "web" / "public" / "demo")
    assert not bundle.manifest.synthetic
    decoder = inference.Decoder(bundle)
    m = bundle.manifest
    w0, w1 = round(m.window.start_s * m.sfreq), round(m.window.end_s * m.sfreq)
    items = {(it["trial"], it["window"]): it for it in bundle.predictions["items"]}
    truth, probs = [], []
    for info in m.trials:
        data = bundle.trial_data(info.index)
        cue = round(info.cue_onset_s * m.sfreq)
        for window, start, label in (("rest", 0, 0), ("imagery", cue, info.label)):
            p, _ = decoder.predict(data[:, start + w0 : start + w1])
            assert np.abs(p - items[(info.index, window)]["probs"]).max() < 1e-4
            truth.append(label)
            probs.append(p)
    summary = json.loads((root / "results" / "summary" / "demo_model.json").read_text())
    from sixthfinger.evaluation.metrics import score

    assert score(np.array(truth), np.array(probs), [0, 1, 2])["bal_acc"] == pytest.approx(
        summary["held_out_bal_acc"], abs=1e-6
    )
