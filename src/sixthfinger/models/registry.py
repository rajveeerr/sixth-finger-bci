"""Method interface shared by every decoder in the protocol registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline


class UndefinedCell(Exception):
    """The method is not defined on this training data; the runner writes the cell as missing
    with this message as its reason, never as a score (protocol 4.2: declared, not dropped)."""


@dataclass
class Batch:
    X: np.ndarray | None  # (n, 40, n_times) float32, volts; None for covariance-only sources
    y: np.ndarray | None  # (n,) int64; None for unlabelled data
    md: pd.DataFrame  # metadata rows aligned with X; its index is the row in the run's arrays
    # The run's CovarianceStore, for methods with uses_covariances (P08 transfer methods).
    store: object | None = None


class Method(Protocol):
    name: str
    uses_source: bool  # True for transfer methods
    # Optional class attributes the runner reads with a default:
    #   deep (False): draws_deep instead of draws_classical
    #   min_trials_per_class (1): below this k the cell is declared undefined, not tried
    #   feature ("bandpower"): the input a within-session run feeds it (protocol 4.1)
    #   uses_covariances (False): sources arrive as covariances from the run's store, X None
    #   needs_classes (False): the runner passes the task's class ids as `classes`
    #   needs_pretrained (False): the runner passes `models_dir` and the experiment's `mirror`

    def fit(
        self,
        target: Batch,
        source: Batch | None = None,
        unlabelled: Batch | None = None,
        seed: int = 0,
    ) -> Method: ...

    def predict_proba(self, X: np.ndarray) -> np.ndarray: ...  # (n, n_classes)


class PipelineMethod:
    """A from-scratch method that is one scikit-learn pipeline fitted on the target windows.

    `paper_replica` relies on `build()`: it fits every step but the last on all windows.
    """

    uses_source = False

    def __init__(self, n_classes: int, **params):
        self.n_classes, self.params = n_classes, params

    def build(self) -> Pipeline:
        raise NotImplementedError

    def fit(self, target: Batch, source=None, unlabelled=None, seed: int = 0):
        self.pipe = self.build().fit(target.X, target.y)
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self.pipe.predict_proba(X)


REGISTRY: dict[str, type] = {}


def register(name: str):
    def deco(cls):
        cls.name = name
        REGISTRY[name] = cls
        return cls

    return deco


def make_method(name: str, n_classes: int, **params) -> Method:
    if name not in REGISTRY:
        raise KeyError(f"Unknown method {name!r}; known: {sorted(REGISTRY)}")
    return REGISTRY[name](n_classes=n_classes, **params)
