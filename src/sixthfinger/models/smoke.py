"""Two deliberately simple decoders that exercise the harness before the real methods exist.

They are never part of a study: `smoke_prior` must score exactly chance and
`smoke_logvar_lda` (log-variance per channel into LDA) a little above it, so a smoke run
that shows anything else points at the harness, not at a model.
"""

from __future__ import annotations

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.dummy import DummyClassifier
from sklearn.pipeline import Pipeline, make_pipeline

from sixthfinger.models.registry import Batch, register


class LogVariance(BaseEstimator, TransformerMixin):
    """X: (n, n_channels, n_times) -> (n, n_channels) log signal variance."""

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        return np.log(np.var(X, axis=-1))


class _PipelineMethod:
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


@register("smoke_logvar_lda")
class SmokeLogVarLda(_PipelineMethod):
    def build(self) -> Pipeline:
        return make_pipeline(
            LogVariance(), LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")
        )


@register("smoke_prior")
class SmokePrior(_PipelineMethod):
    def build(self) -> Pipeline:
        # Predicts the training-class prior: balanced accuracy is exactly 1 / n_classes.
        return make_pipeline(LogVariance(), DummyClassifier(strategy="prior"))
