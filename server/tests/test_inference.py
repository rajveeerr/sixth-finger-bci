import json

import numpy as np
import pytest

from app.gate import CommandGate
from app.inference import Decoder, softmax
from app.stream import trial_timeline


def test_softmax_is_stable_for_large_logits():
    probs = softmax(np.array([1000.0, 1001.0, 999.0]))
    assert np.isclose(probs.sum(), 1.0)
    assert probs.argmax() == 1


def test_decoder_returns_probabilities(bundle):
    decoder = Decoder(bundle)
    data = bundle.trial_data(0)
    probs, latency = decoder.predict(data[:, 250:1250])
    assert probs.shape == (3,)
    assert np.isclose(probs.sum(), 1.0, atol=1e-5)
    assert latency >= 0


def test_decoder_rejects_wrong_window(bundle):
    with pytest.raises(ValueError):
        Decoder(bundle).predict(np.zeros((40, 999), dtype=np.float32))


def test_precomputed_predictions_match_live_decoding(bundle):
    decoder = Decoder(bundle)
    stored = {(p["trial"], p["window"]): p for p in bundle.predictions["items"]}
    for info in bundle.manifest.trials:
        data = bundle.trial_data(info.index)
        cue = round(info.cue_onset_s * bundle.manifest.sfreq)
        for window, start in (("rest", 0), ("imagery", cue)):
            probs, _ = decoder.predict(data[:, start + 250 : start + 1250])
            np.testing.assert_allclose(probs, stored[(info.index, window)]["probs"], atol=1e-4)


def test_fixture_model_separates_synthetic_classes(bundle):
    labels = {(p["trial"], p["window"]): p["label_id"] for p in bundle.predictions["items"]}
    for info in bundle.manifest.trials:
        assert labels[(info.index, "rest")] == 0
        assert labels[(info.index, "imagery")] == info.label


def test_timeline_matches_training_windows(bundle):
    info = bundle.manifest.trials[0]
    events = trial_timeline(info, 250.0, bundle.manifest.window)
    cue = round(info.cue_onset_s * 250)
    decodes = {e.window: (e.sample, e.start, e.stop) for e in events if e.kind == "decode"}
    assert decodes["rest"] == (1250, 250, 1250)
    assert decodes["imagery"] == (cue + 1250, cue + 250, cue + 1250)
    phases = [(e.phase, e.sample) for e in events if e.kind == "phase"]
    assert phases == [("rest", 0), ("prepare", cue - 250), ("imagery", cue)]


GATE_VECTORS = json.loads(
    """
    {"probs": [[0.8,0.1,0.1],[0.1,0.1,0.8],[0.05,0.05,0.9],[0.05,0.05,0.9],[0.1,0.1,0.8],
               [0.9,0.05,0.05],[0.9,0.05,0.05],[0.9,0.05,0.05],[0.1,0.85,0.05],[0.05,0.9,0.05],
               [0.05,0.9,0.05],[0.05,0.9,0.05]],
     "active": [0, 0, 0, 0, 2, 2, 0, 0, 0, 0, 0, 1]}
    """
)


def test_gate_needs_dwell_and_releases():
    gate = CommandGate()
    active = [gate.update(np.array(p)) for p in GATE_VECTORS["probs"]]
    assert active == GATE_VECTORS["active"]
