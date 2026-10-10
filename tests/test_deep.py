import json

import numpy as np
import pandas as pd
import pytest
import torch

from sixthfinger.config import load_data_config
from sixthfinger.evaluation.runner import method_params
from sixthfinger.models import deep
from sixthfinger.models.registry import Batch, make_method
from sixthfinger.paths import get_paths

# Tiny and on the CPU: the tests check plumbing, not accuracy.
TINY = {"max_epochs": 2, "device": "cpu"}


def _params(name: str, **over) -> dict:
    return {**method_params(name, get_paths().configs), **over}


def _windows(n_per_class=6, labels=(0, 1, 2), n_ch=40, n_t=200, seed=0):
    rng = np.random.default_rng(seed)
    y = np.repeat(labels, n_per_class)
    X = rng.standard_normal((len(y), n_ch, n_t)).astype(np.float32) * 1e-6
    for i, lab in enumerate(labels):
        X[y == lab, i] *= 3  # a little signal per class
    md = pd.DataFrame({"trial_uid": [f"t{i}" for i in range(len(y))], "label": y})
    return X, y, md


def test_configs_hold_the_preregistered_recipe():
    # Pre-registration 3.6; any change here is a deviation and must be logged.
    p = _params("eegnet_scratch")
    assert p["architecture"] == "EEGNet" and p["architecture_params"] == {}
    assert p["optimizer"] == {"name": "AdamW", "lr": 1e-3, "weight_decay": 1e-3}
    assert (p["batch_size"], p["max_epochs"], p["input_scale"]) == (32, 150, 1e6)
    assert p["scheduler"] == "CosineAnnealingLR"
    ea = _params("eegnet_ea_ft")
    assert ea["pretrain"] == {
        "max_epochs": 150,
        "early_stopping_patience": 20,
        "validation_subjects": 3,
        "seed": 0,
    }
    assert ea["finetune_grid"] == {"lr": [1e-4, 3e-4], "epochs": [20, 50]}
    assert ea["alignment"] == {"rel_floor": 1e-6}
    for key in ("architecture", "architecture_params", "optimizer", "batch_size", "input_scale"):
        assert ea[key] == p[key]


def test_task_label_map_turns_t3_ids_into_positions_and_back():
    pos, back = deep.task_label_map(np.array([0, 2, 2, 0]))
    assert pos.tolist() == [0, 1, 1, 0]
    assert back == {0: 0, 1: 2}


@pytest.mark.parametrize("labels", [(0, 1, 2), (0, 2)])
def test_predict_proba_shape_and_rows_sum_to_one(labels):
    X, y, md = _windows(labels=labels)
    m = make_method("eegnet_scratch", n_classes=len(labels), **_params("eegnet_scratch", **TINY))
    proba = m.fit(Batch(X, y, md), seed=0).predict_proba(X)
    assert proba.shape == (len(y), len(labels))
    np.testing.assert_allclose(proba.sum(axis=1), 1.0, atol=1e-5)


def test_same_seed_gives_identical_predictions_on_cpu():
    X, y, md = _windows()
    params = _params("eegnet_scratch", **TINY)
    a = make_method("eegnet_scratch", n_classes=3, **params).fit(Batch(X, y, md), seed=3)
    b = make_method("eegnet_scratch", n_classes=3, **params).fit(Batch(X, y, md), seed=3)
    np.testing.assert_array_equal(a.predict_proba(X), b.predict_proba(X))


def test_saved_weights_load_into_a_fresh_network_with_identical_outputs(tmp_path):
    X, y, md = _windows()
    cfg = _params("eegnet_scratch", **TINY)
    m = make_method("eegnet_scratch", n_classes=3, **cfg).fit(Batch(X, y, md), seed=0)
    torch.save(m.clf.module_.state_dict(), tmp_path / "w.pt")
    net = deep.build_module(cfg, 40, 3, X.shape[-1])
    net.load_state_dict(torch.load(tmp_path / "w.pt", weights_only=True))
    net.eval()
    with torch.no_grad():
        logits = net(torch.from_numpy(m._x(X)))
    np.testing.assert_allclose(
        torch.softmax(logits, dim=1).numpy(), m.predict_proba(X), rtol=1e-4, atol=1e-6
    )


def _cohort(subjects):
    frames, Xs = [], []
    for i, s in enumerate(subjects):
        X, _, md = _windows(n_per_class=4, seed=i)
        frames.append(md.assign(subject=s))
        Xs.append(X)
    return np.concatenate(Xs), pd.concat(frames, ignore_index=True)


def test_pretraining_never_sees_the_target_or_its_linked_partner(tmp_path):
    data_cfg = load_data_config()
    X, md = _cohort(data_cfg.subjects.ids)
    cfg = _params("eegnet_ea_ft", device="cpu")
    cfg["pretrain"] = {**cfg["pretrain"], "max_epochs": 2}
    ready = deep.prepare_inputs(X, md.subject.to_numpy(), cfg, aligned=True)
    entry = deep.pretrain_loso("sub-21", cfg, ready, md, data_cfg, tmp_path)
    used = set(entry["train_subjects"]) | set(entry["validation_subjects"])
    assert "sub-21" not in used and "sub-22" not in used  # linked pair
    assert len(entry["validation_subjects"]) == 3
    assert (tmp_path / "eegnet_loso_sub-21_ea_raw.pt").exists()
    assert entry["epochs_run"] == len(entry["history"]) <= 2
    deep.write_manifest([entry], tmp_path / "manifest.json")
    assert "eegnet_loso_sub-21_ea_raw.pt" in json.loads((tmp_path / "manifest.json").read_text())


def test_pretraining_refuses_a_target_inside_its_sources(tmp_path, monkeypatch):
    data_cfg = load_data_config()
    X, md = _cohort(data_cfg.subjects.ids)
    cfg = _params("eegnet_ea_ft", device="cpu")
    monkeypatch.setattr(
        deep, "pretrain_sources", lambda target, data_cfg: list(data_cfg.subjects.ids)
    )
    ready = deep.prepare_inputs(X, md.subject.to_numpy(), cfg, aligned=False)
    with pytest.raises(AssertionError, match="own pre-training data"):
        deep.pretrain_loso("sub-07", cfg, ready, md, data_cfg, tmp_path)


def test_inputs_are_aligned_per_subject_then_scaled_to_microvolts():
    X, md = _cohort(["sub-01", "sub-03"])
    cfg = _params("eegnet_ea_ft")
    ready = deep.prepare_inputs(X, md.subject.to_numpy(), cfg, aligned=True)
    for s in ("sub-01", "sub-03"):
        A = ready[(md.subject == s).to_numpy()].astype(np.float64) / cfg["input_scale"]
        w = np.linalg.eigvalsh(np.einsum("nct,ndt->cd", A, A) / (A.shape[0] * A.shape[-1]))
        np.testing.assert_allclose(w, 1.0, atol=1e-3)
    raw = deep.prepare_inputs(X, md.subject.to_numpy(), cfg, aligned=False)
    np.testing.assert_allclose(raw, X * 1e6, rtol=1e-6)
