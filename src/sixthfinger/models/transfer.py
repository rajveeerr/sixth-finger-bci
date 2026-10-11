"""Transfer decoders that also learn from the other subjects (P08, protocol 5).

The Riemannian methods re-centre every subject to the identity as pyRiemann's `TLCenter`
does, then fit one classifier on the source and target matrices together with the target
weighted, as `TLClassifier` does. They read the run's cached covariances; each source
subject is re-centred once over all its windows of the task's classes. The target is
re-centred with its unlabelled set only (protocol 4.2), never with its test windows.
Their Riemannian means (tangent-space reference, MDM class means) start from the sources'
own mean, cached per target: the same fixed point within the solver's tolerance, reached in
a few iterations instead of about twenty. `tests/test_transfer.py` checks the predictions
against the pyRiemann pipeline.
"""

from __future__ import annotations

import numpy as np
import torch
from pyriemann.classification import MDM
from pyriemann.estimation import Covariances
from pyriemann.geometry.mean import mean_riemann
from pyriemann.tangentspace import TangentSpace
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline

from sixthfinger.models.deep import (
    _DeepMethod,
    build_module,
    make_finetune_classifier,
    pretrained_path,
)
from sixthfinger.models.registry import Batch, register
from sixthfinger.preprocessing.alignment import align, reference_matrix
from sixthfinger.preprocessing.covariance import centring_filters, fingerprint, recentre


def _covs(batch: Batch, estimator: str) -> np.ndarray:
    if batch.store is not None:
        if batch.store.estimator != estimator:
            raise ValueError(f"the run's covariances are {batch.store.estimator}, not {estimator}")
        return batch.store.covs(batch.md.index)
    return Covariances(estimator).transform(batch.X)


def _labelled(batch: Batch | None) -> bool:
    return batch is not None and batch.y is not None and len(batch.y) > 0


class WarmTangentSpace(TangentSpace):
    """pyRiemann's TangentSpace (Riemannian metric) whose reference mean starts at `init`."""

    def __init__(self, metric="riemann", tsupdate=False, init=None):
        super().__init__(metric=metric, tsupdate=tsupdate)
        self.init = init

    def fit(self, X, y=None, sample_weight=None):
        if self.metric != "riemann":
            raise ValueError("the warm start is for the Riemannian mean only")
        self.reference_ = mean_riemann(X, sample_weight=sample_weight, init=self.init)
        return self

    def fit_transform(self, X, y=None, sample_weight=None):
        return self.fit(X, y, sample_weight=sample_weight).transform(X)


class WarmMDM(MDM):
    """pyRiemann's MDM (Riemannian metric) whose class means start at `init[class]`."""

    def __init__(self, metric="riemann", n_jobs=1, init=None):
        super().__init__(metric=metric, n_jobs=n_jobs)
        self.init = init

    def fit(self, X, y, sample_weight=None):
        if self.metric != "riemann":
            raise ValueError("the warm start is for the Riemannian mean only")
        self._metric_mean = self._metric_dist = "riemann"  # what MDM.fit sets for "riemann"
        w = np.ones(len(X)) if sample_weight is None else np.asarray(sample_weight)
        self.classes_ = np.unique(y)
        start = self.init or {}
        self.covmeans_ = np.stack(
            [
                mean_riemann(X[y == c], sample_weight=w[y == c], init=start.get(int(c)))
                for c in self.classes_
            ]
        )
        return self


class _RiemannTransfer:
    uses_source = True
    uses_covariances = True

    def __init__(self, n_classes: int, **params):
        self.n_classes, self.p = n_classes, params

    def _estimator(self, Cs: np.ndarray, ys: np.ndarray, key: tuple):
        raise NotImplementedError

    def _fit_args(self, weights: np.ndarray) -> dict:
        raise NotImplementedError

    def fit(self, target: Batch, source: Batch | None = None, unlabelled=None, seed: int = 0):
        if source is None or unlabelled is None or not len(unlabelled.md):
            raise ValueError(f"{self.name} needs source data and the target's unlabelled set")
        if self.p.get("target_weight") is None:
            raise ValueError(f"{self.name}: target_weight not chosen yet (P08 step 4.5)")
        est = self.p["covariance"]
        classes = sorted(int(c) for c in np.unique(source.md.label))
        Cs = source.store.recentred(source.md.index, classes)
        key = (fingerprint(source.md.index), tuple(classes))
        # Target reference from the unlabelled set: the drawn windows at k > 0, the declared
        # REST set at k = 0 (protocol 4.2, deviation log 2026-10-11).
        self.W = centring_filters(_covs(unlabelled, est))
        parts, ys, ws = [Cs], [source.y], [np.ones(len(source.y))]
        if _labelled(target):
            parts.append(recentre(_covs(target, est), self.W))
            ys.append(target.y)
            ws.append(np.full(len(target.y), float(self.p["target_weight"])))
        X, y, w = np.concatenate(parts), np.concatenate(ys), np.concatenate(ws)
        self.store = source.store
        self.model = self._estimator(Cs, source.y, key).fit(X, y, **self._fit_args(w))
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        C = Covariances(self.p["covariance"]).transform(X)
        return self.model.predict_proba(recentre(C, self.W))


@register("rct_mdm")
class RctMdm(_RiemannTransfer):
    def _estimator(self, Cs, ys, key):
        init = self.store.cached(
            ("rct_mdm", *key),
            lambda: {int(c): mean_riemann(Cs[ys == c]) for c in np.unique(ys)},
        )
        return WarmMDM(metric=self.p["metric"], init=init)

    def _fit_args(self, weights):
        return {"sample_weight": weights}


@register("rct_tslr")
class RctTslr(_RiemannTransfer):
    def _estimator(self, Cs, ys, key):
        init = self.store.cached(("rct_tslr", *key), lambda: mean_riemann(Cs))
        lr = self.p["logreg"]
        return make_pipeline(
            WarmTangentSpace(metric=self.p["tangent_space_metric"], init=init),
            LogisticRegression(C=lr["C"], max_iter=lr["max_iter"]),
        )

    def _fit_args(self, weights):
        # TLClassifier passes the domain weights to every step that takes sample_weight.
        return {
            "warmtangentspace__sample_weight": weights,
            "logisticregression__sample_weight": weights,
        }


@register("pooled_tslr")
class PooledTslr:
    """`ts_lr` on the source and target windows together, without any alignment."""

    uses_source = True
    uses_covariances = True

    def __init__(self, n_classes: int, **params):
        self.n_classes, self.p = n_classes, params

    def fit(self, target: Batch, source: Batch | None = None, unlabelled=None, seed: int = 0):
        if source is None:
            raise ValueError("pooled_tslr needs source data")
        est = self.p["covariance"]
        Cs = _covs(source, est)
        parts, ys = [Cs], [source.y]
        if _labelled(target):
            parts.append(_covs(target, est))
            ys.append(target.y)
        init = None
        if source.store is not None:
            key = ("pooled_tslr", fingerprint(source.md.index))
            init = source.store.cached(key, lambda: mean_riemann(Cs))
        lr = self.p["logreg"]
        self.model = make_pipeline(
            WarmTangentSpace(metric=self.p["tangent_space_metric"], init=init),
            LogisticRegression(C=lr["C"], max_iter=lr["max_iter"]),
        ).fit(np.concatenate(parts), np.concatenate(ys))
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self.model.predict_proba(Covariances(self.p["covariance"]).transform(X))


@register("eegnet_ea_ft")
class EegnetEaFinetune(_DeepMethod):
    """The target's own leave-one-subject-out EEGNet (P07), all layers fine-tuned.

    The sources are already in the pre-trained model, so the runner loads none. The network
    keeps its three outputs for every task: it trains on the task's windows with their
    three-class ids and answers with the task's columns, renormalised (deviation log
    2026-10-11), so S1 k = 0 is P07's zero-shot.
    """

    needs_pretrained = True
    N_OUTPUTS = 3

    def __init__(
        self, n_classes, classes=None, models_dir=None, mirror=False, permuted=False, **cfg
    ):
        super().__init__(n_classes, classes, **cfg)
        if classes is None or models_dir is None:
            raise ValueError("eegnet_ea_ft needs the task's classes and the models directory")
        self.models_dir, self.mirror, self.permuted = models_dir, mirror, permuted

    def fit(self, target: Batch, source=None, unlabelled=None, seed: int = 0):
        cfg = self.cfg
        if cfg.get("finetune_lr") is None or cfg.get("finetune_epochs") is None:
            raise ValueError("eegnet_ea_ft: fine-tuning values not chosen yet (P08 step 4.5)")
        if unlabelled is None or not len(unlabelled.md):
            raise ValueError("eegnet_ea_ft needs the target's unlabelled set for its alignment")
        subject = unlabelled.md.subject.iloc[0]
        self.R = reference_matrix(unlabelled.X, cfg["alignment"]["rel_floor"])
        _, c, t = unlabelled.X.shape
        net = build_module(cfg, c, self.N_OUTPUTS, t)
        path = pretrained_path(self.models_dir, subject, self.mirror, self.permuted)
        net.load_state_dict(torch.load(path, weights_only=True, map_location="cpu"))
        epochs = int(cfg["finetune_epochs"])
        self.clf = make_finetune_classifier(
            cfg, net, self.N_OUTPUTS, epochs, float(cfg["finetune_lr"]), seed=seed
        )
        if _labelled(target):
            if set(target.md.subject) != {subject}:
                raise ValueError("labelled and unlabelled windows from different subjects")
            self.clf.fit(self._x(align(target.X, self.R)), target.y.astype(np.int64))
        else:
            self.clf.initialize()  # k = 0: the aligned pre-trained model as it is
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        proba = self.clf.predict_proba(self._x(align(X, self.R)))[:, self.classes]
        return proba / proba.sum(axis=1, keepdims=True)
