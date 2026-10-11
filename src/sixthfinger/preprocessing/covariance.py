"""Covariances of the cached windows, computed once, and each subject re-centred once.

The Riemannian transfer methods of P08 fit on about 9 000 source windows per target. The
windows' covariances and each source subject's re-centring depend on neither the target, the
budget nor the draw, so a run computes them once instead of in every fit (`DECISIONS.md` 58).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable

import numpy as np
import pandas as pd
from pyriemann.estimation import Covariances
from pyriemann.geometry.base import invsqrtm
from pyriemann.geometry.mean import gmean


def centring_filters(C: np.ndarray) -> np.ndarray:
    """pyRiemann's `TLCenter` for one domain: inverse square root of the Riemannian mean."""
    return invsqrtm(gmean(C, metric="riemann"))


def recentre(C: np.ndarray, W: np.ndarray) -> np.ndarray:
    """Whiten covariances with a domain's filters, so that domain's mean becomes the identity."""
    return W.T @ C @ W


class CovarianceStore:
    """The covariance of every cached window, by row position of the run's metadata."""

    def __init__(self, X: np.ndarray, md: pd.DataFrame, estimator: str = "oas", chunk: int = 500):
        self.estimator = estimator
        self.subject = md.subject.to_numpy()
        self.label = md.label.to_numpy()
        est = Covariances(estimator)
        self.C = np.concatenate([est.transform(X[i : i + chunk]) for i in range(0, len(X), chunk)])
        self._filters: dict[tuple, np.ndarray] = {}
        self._cache: dict[tuple, object] = {}

    def covs(self, idx) -> np.ndarray:
        return self.C[np.asarray(idx)]

    def filters(self, subject: str, classes) -> np.ndarray:
        """A source subject's filters over all of its windows of these classes, all sessions.

        The same set the runner hands a transfer method as that subject's source data, so the
        result is what `TLCenter` would compute from it. Never used for the target: its
        reference comes from the calibration windows only (protocol 4.2).
        """
        key = (subject, tuple(sorted(int(c) for c in classes)))
        if key not in self._filters:
            rows = (self.subject == subject) & np.isin(self.label, key[1])
            self._filters[key] = centring_filters(self.C[rows])
        return self._filters[key]

    def recentred(self, idx, classes) -> np.ndarray:
        idx = np.asarray(idx)
        out = np.empty((len(idx), *self.C.shape[1:]))
        subjects = self.subject[idx]
        for s in np.unique(subjects):
            rows = subjects == s
            out[rows] = recentre(self.C[idx[rows]], self.filters(s, classes))
        return out

    def cached(self, key: tuple, compute: Callable[[], object]) -> object:
        """A value computed once per process, e.g. the sources' own mean (a warm start)."""
        if key not in self._cache:
            self._cache[key] = compute()
        return self._cache[key]


def fingerprint(idx) -> str:
    """Short id of a set of row positions, to key what depends on exactly those rows."""
    return hashlib.blake2b(np.asarray(idx, dtype=np.int64).tobytes(), digest_size=8).hexdigest()
