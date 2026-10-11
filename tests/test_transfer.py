import numpy as np
import pandas as pd
import pytest
import torch
from pyriemann.classification import MDM
from pyriemann.estimation import Covariances
from pyriemann.tangentspace import TangentSpace
from pyriemann.transfer import TLCenter, TLClassifier, encode_domains
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline

from sixthfinger.evaluation.runner import method_params
from sixthfinger.models import deep, transfer
from sixthfinger.models.registry import Batch, make_method
from sixthfinger.paths import get_paths
from sixthfinger.preprocessing.alignment import align, reference_matrix
from sixthfinger.preprocessing.covariance import CovarianceStore, centring_filters

CLASSES = [0, 1, 2]


def _cohort(subjects=("s1", "s2", "s3", "tg"), n_per_class=12, n_ch=6, n_t=128, seed=0):
    """Windows with a class signal and a subject-specific mixing, as real subjects differ."""
    rng = np.random.default_rng(seed)
    Xs, rows = [], []
    for si, s in enumerate(subjects):
        mix = np.eye(n_ch) + 0.3 * rng.standard_normal((n_ch, n_ch))
        for c in CLASSES:
            x = rng.standard_normal((n_per_class, n_ch, n_t))
            x[:, c] *= 2.5  # class signal on one channel
            Xs.append(np.einsum("cd,ndt->nct", mix * (1 + si / 4), x))
            rows += [{"subject": s, "label": c, "run": 1 + (i % 2)} for i in range(n_per_class)]
    md = pd.DataFrame(rows)
    return np.concatenate(Xs).astype(np.float32), md


def _batches(X, md, store, target="tg"):
    src = md[md.subject != target]
    tg = md[md.subject == target]
    train, test = tg[tg.run == 1], tg[tg.run == 2]
    source = Batch(None, src.label.to_numpy(), src, store=store)
    labelled = Batch(X[train.index], train.label.to_numpy(), train, store=store)
    unlabelled = Batch(X[train.index], None, train.drop(columns="label"), store=store)
    return source, labelled, unlabelled, X[test.index]


def _pyriemann_reference(X, md, estimator, weight, target="tg"):
    src, tg = md[md.subject != target], md[(md.subject == target) & (md.run == 1)]
    test = md[(md.subject == target) & (md.run == 2)]
    cov = Covariances("oas")
    C = cov.transform(X[np.concatenate([src.index, tg.index])])
    y = np.concatenate([src.label, tg.label])
    domains = np.concatenate([src.subject, ["target"] * len(tg)])
    X_enc, y_enc = encode_domains(C, y, domains)
    weights = {s: 1.0 for s in src.subject.unique()} | {"target": weight}
    pipe = make_pipeline(
        TLCenter(target_domain="target"),
        TLClassifier(target_domain="target", estimator=estimator, domain_weight=weights),
    )
    return pipe.fit(X_enc, y_enc).predict_proba(cov.transform(X[test.index]))


@pytest.mark.parametrize("weight", [1.0, 5.0])
def test_rct_tslr_equals_the_pyriemann_pipeline(weight):
    X, md = _cohort()
    store = CovarianceStore(X, md)
    source, labelled, unlabelled, X_test = _batches(X, md, store)
    params = {**method_params("rct_tslr", get_paths().configs), "target_weight": weight}
    ours = make_method("rct_tslr", n_classes=3, **params).fit(labelled, source, unlabelled)
    est = make_pipeline(TangentSpace(metric="riemann"), LogisticRegression(C=1.0, max_iter=1000))
    ref = _pyriemann_reference(X, md, est, weight)
    np.testing.assert_allclose(ours.predict_proba(X_test), ref, atol=1e-6)


def test_rct_mdm_equals_the_pyriemann_pipeline():
    X, md = _cohort(seed=1)
    store = CovarianceStore(X, md)
    source, labelled, unlabelled, X_test = _batches(X, md, store)
    params = {**method_params("rct_mdm", get_paths().configs), "target_weight": 5.0}
    ours = make_method("rct_mdm", n_classes=3, **params).fit(labelled, source, unlabelled)
    ref = _pyriemann_reference(X, md, MDM(metric="riemann"), 5.0)
    np.testing.assert_allclose(ours.predict_proba(X_test), ref, atol=1e-6)


def test_the_target_reference_comes_from_the_unlabelled_set_only():
    X, md = _cohort(seed=2)
    store = CovarianceStore(X, md)
    source, labelled, unlabelled, X_test = _batches(X, md, store)
    rest = unlabelled.md[md.label[unlabelled.md.index] == 0]  # e.g. the k = 0 REST set
    rest_only = Batch(X[rest.index], None, rest, store=store)
    params = {**method_params("rct_tslr", get_paths().configs), "target_weight": 1.0}
    m = make_method("rct_tslr", n_classes=3, **params).fit(labelled, source, rest_only)
    np.testing.assert_allclose(m.W, centring_filters(store.covs(rest.index)))
    # k = 0: no labelled target window, the classifier sees the sources only.
    empty = Batch(X[:0], np.array([], int), md.iloc[:0], store=store)
    m0 = make_method("rct_tslr", n_classes=3, **params).fit(empty, source, rest_only)
    proba = m0.predict_proba(X_test)
    assert proba.shape == (len(X_test), 3)
    np.testing.assert_allclose(proba.sum(axis=1), 1.0)


def test_transfer_methods_refuse_unchosen_target_weights():
    X, md = _cohort()
    store = CovarianceStore(X, md)
    source, labelled, unlabelled, _ = _batches(X, md, store)
    m = make_method("rct_tslr", n_classes=3, **method_params("rct_tslr", get_paths().configs))
    with pytest.raises(ValueError, match="target_weight"):
        m.fit(labelled, source, unlabelled)


def test_pooled_tslr_equals_ts_lr_on_the_pooled_windows():
    X, md = _cohort(seed=3)
    store = CovarianceStore(X, md)
    source, labelled, unlabelled, X_test = _batches(X, md, store)
    params = method_params("pooled_tslr", get_paths().configs)
    ours = make_method("pooled_tslr", n_classes=3, **params).fit(labelled, source, unlabelled)
    rows = np.concatenate([source.md.index, labelled.md.index])
    ref = make_pipeline(
        Covariances("oas"),
        TangentSpace(metric="riemann"),
        LogisticRegression(C=1.0, max_iter=1000),
    ).fit(X[rows], md.label.to_numpy()[rows])
    np.testing.assert_allclose(ours.predict_proba(X_test), ref.predict_proba(X_test), atol=1e-6)


# EEGNet fine-tuning -------------------------------------------------------------------------

N_CH, N_T = 8, 256


def _ft_cfg(**over):
    cfg = {**method_params("eegnet_ea_ft", get_paths().configs), "device": "cpu"}
    return {**cfg, "finetune_lr": 3e-4, "finetune_epochs": 3, **over}


@pytest.fixture
def models_dir(tmp_path):
    torch.manual_seed(0)
    net = deep.build_module(_ft_cfg(), N_CH, 3, N_T)
    torch.save(net.state_dict(), tmp_path / deep.pretrained_name("sub-07", False, True))
    return tmp_path


def _target(n_trials, classes, seed=0):
    rng = np.random.default_rng(seed)
    y = np.resize(np.asarray(classes), n_trials * len(classes))
    X = (rng.standard_normal((len(y), N_CH, N_T)) * 1e-5).astype(np.float32)
    md = pd.DataFrame({"subject": "sub-07", "label": y})
    return X, y, md


def _ft(models_dir, classes, **cfg):
    return make_method(
        "eegnet_ea_ft",
        n_classes=len(classes),
        classes=classes,
        models_dir=models_dir,
        **_ft_cfg(**cfg),
    )


@pytest.mark.parametrize("classes", [[0, 1, 2], [0, 2]])
def test_k0_answers_with_the_pretrained_network_on_aligned_windows(models_dir, classes):
    X, _, md = _target(10, [0])
    m = _ft(models_dir, classes).fit(Batch(X[:0], np.array([], int), md.iloc[:0]), None,
                                     Batch(X, None, md.drop(columns="label")))  # fmt: skip
    net = deep.build_module(_ft_cfg(), N_CH, 3, N_T)
    net.load_state_dict(torch.load(models_dir / deep.pretrained_name("sub-07", False, True)))
    net.eval()
    x = align(X, reference_matrix(X)) * 1e6
    with torch.no_grad():
        p = torch.softmax(net(torch.from_numpy(x.astype(np.float32))), dim=1).numpy()[:, classes]
    np.testing.assert_allclose(m.predict_proba(X), p / p.sum(axis=1, keepdims=True), atol=1e-5)


def test_fine_tuning_starts_from_the_loaded_weights_and_trains_every_layer(models_dir):
    X, y, md = _target(2, [0, 1, 2])  # k = 2: 6 windows, less than one batch
    loaded = torch.load(models_dir / deep.pretrained_name("sub-07", False, True))
    m = _ft(models_dir, [0, 1, 2])
    m.fit(Batch(X, y, md), None, Batch(X, None, md.drop(columns="label")), seed=0)
    hist = m.clf.history
    assert [h["train_batch_count"] for h in hist] == [1, 1, 1]
    state = m.clf.module_.state_dict()
    changed = {
        k for k, v in loaded.items() if v.dtype.is_floating_point and not torch.equal(v, state[k])
    }
    assert any(k.startswith("conv_temporal") for k in changed)
    assert any(k.startswith("final_layer") for k in changed)
    # Starting point: a zero learning rate leaves the loaded weights exactly as they were.
    m0 = _ft(models_dir, [0, 1, 2], finetune_lr=0.0)
    m0.fit(Batch(X, y, md), None, Batch(X, None, md.drop(columns="label")), seed=0)
    s0 = m0.clf.module_.state_dict()
    params = [k for k, v in loaded.items() if "running" not in k and "num_batches" not in k]
    assert all(torch.equal(loaded[k], s0[k]) for k in params)


def test_t3_fine_tuning_keeps_three_outputs_and_answers_with_two_columns(models_dir):
    X, y, md = _target(3, [0, 2])
    m = _ft(models_dir, [0, 2]).fit(Batch(X, y, md), None, Batch(X, None, md))
    proba = m.predict_proba(X)
    assert proba.shape == (len(X), 2)
    np.testing.assert_allclose(proba.sum(axis=1), 1.0, atol=1e-6)
    assert m.clf.module_.final_layer.conv_classifier.weight.shape[0] == 3


def test_fine_tuning_refuses_a_target_without_its_own_pretrained_model(models_dir):
    X, y, md = _target(2, [0, 1, 2])
    md = md.assign(subject="sub-09")
    with pytest.raises(FileNotFoundError, match="sub-09"):
        _ft(models_dir, [0, 1, 2]).fit(Batch(X, y, md), None, Batch(X, None, md))
    assert transfer.EegnetEaFinetune.uses_source is False
