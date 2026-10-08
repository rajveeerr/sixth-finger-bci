"""CSP and Riemannian decoders with the hyperparameters of the pre-registration (3.6).

The values themselves live in configs/models/<name>.yaml and arrive here as `params`.
"""

from __future__ import annotations

import warnings
from functools import partial

import mne
from mne.decoding import CSP
from pyriemann.classification import MDM
from pyriemann.estimation import Covariances
from pyriemann.tangentspace import TangentSpace
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.feature_selection import SelectKBest, mutual_info_classif
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, make_pipeline, make_union
from sklearn.svm import SVC

from sixthfinger.models.registry import PipelineMethod, register
from sixthfinger.preprocessing.filters import BandPass

# MNE logs a few lines per CSP fit; an RQ1 run makes tens of thousands of fits.
mne.set_log_level("ERROR")
# The pre-registration fixes SVC(probability=True); the pinned scikit-learn 1.9 still supports
# it and warns on every fit that a later release will not.
warnings.filterwarnings("ignore", message="The `probability` parameter", category=FutureWarning)


def _csp(p: dict) -> CSP:
    return CSP(n_components=p["n_components"], reg=p["reg"], log=p["log"])


def _lda(p: dict) -> LinearDiscriminantAnalysis:
    return LinearDiscriminantAnalysis(**p)


@register("csp_lda")
class CspLda(PipelineMethod):
    # A class covariance from one trial is not an estimate (protocol 4.2: declared, not tried).
    min_trials_per_class = 2

    def build(self) -> Pipeline:
        return make_pipeline(_csp(self.params["csp"]), _lda(self.params["lda"]))


@register("csp_lda_replica")
class CspLdaReplica(CspLda):
    """The authors' Step7 pipeline on the mu ERSP input; RQ1 sanity check only."""

    feature = "ersp_mu"


@register("csp_svm")
class CspSvm(PipelineMethod):
    min_trials_per_class = 2

    def build(self) -> Pipeline:
        return make_pipeline(_csp(self.params["csp"]), SVC(**self.params["svm"]))


@register("fbcsp_lda")
class FbcspLda(PipelineMethod):
    min_trials_per_class = 2

    def build(self) -> Pipeline:
        p = self.params
        bank = make_union(
            *[
                make_pipeline(BandPass(lo, hi, p["sfreq"], p["filter_order"]), _csp(p["csp"]))
                for lo, hi in p["bands"]
            ]
        )
        score = partial(mutual_info_classif, random_state=p["mutual_info_random_state"])
        return make_pipeline(bank, SelectKBest(score, k=p["select_k"]), _lda(p["lda"]))


@register("mdm")
class Mdm(PipelineMethod):
    def build(self) -> Pipeline:
        return make_pipeline(
            Covariances(self.params["covariance"]), MDM(metric=self.params["metric"])
        )


@register("ts_lr")
class TsLr(PipelineMethod):
    def build(self) -> Pipeline:
        lr = self.params["logreg"]
        return make_pipeline(
            Covariances(self.params["covariance"]),
            TangentSpace(metric=self.params["tangent_space_metric"]),
            LogisticRegression(C=lr["C"], max_iter=lr["max_iter"]),
        )
