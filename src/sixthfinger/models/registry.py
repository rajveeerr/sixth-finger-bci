"""Method interface shared by every decoder in the protocol registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd


@dataclass
class Batch:
    X: np.ndarray  # (n, 40, n_times) float32, volts
    y: np.ndarray | None  # (n,) int64; None for unlabelled data
    md: pd.DataFrame  # metadata rows aligned with X


class Method(Protocol):
    name: str
    uses_source: bool  # True for transfer methods
    # Optional class attributes the runner reads with a default:
    #   deep (False): draws_deep instead of draws_classical
    #   min_trials_per_class (1): below this k the cell is declared undefined, not tried

    def fit(
        self,
        target: Batch,
        source: Batch | None = None,
        unlabelled: Batch | None = None,
        seed: int = 0,
    ) -> Method: ...

    def predict_proba(self, X: np.ndarray) -> np.ndarray: ...  # (n, n_classes)


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
