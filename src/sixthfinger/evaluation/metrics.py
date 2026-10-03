"""Classification metrics reported for every evaluated model."""

from __future__ import annotations

import json

import numpy as np
from scipy.stats import binom
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    cohen_kappa_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

SF = 2  # label id of sixth_finger


def score(y_true: np.ndarray, proba: np.ndarray, classes: list[int]) -> dict:
    """Metric row of one evaluated model.

    y_true holds the task's original label ids; proba is (n, len(classes)), columns
    ordered like `classes`.
    """
    y_pred = np.asarray(classes)[proba.argmax(axis=1)]
    row = {
        "bal_acc": balanced_accuracy_score(y_true, y_pred),
        "acc": accuracy_score(y_true, y_pred),
        "f1_macro": f1_score(y_true, y_pred, average="macro", labels=classes, zero_division=0),
        "kappa": cohen_kappa_score(y_true, y_pred, labels=classes),
        "confusion": json.dumps(confusion_matrix(y_true, y_pred, labels=classes).tolist()),
        "sf_recall": np.nan,
        "sf_precision": np.nan,
        "auc_sf": np.nan,
    }
    if SF in classes:
        is_sf, said_sf = y_true == SF, y_pred == SF
        row["sf_recall"] = recall_score(is_sf, said_sf, zero_division=0)
        row["sf_precision"] = precision_score(is_sf, said_sf, zero_division=0)
        if len(np.unique(is_sf)) == 2:
            row["auc_sf"] = roc_auc_score(is_sf, proba[:, classes.index(SF)])
    return {k: (float(v) if isinstance(v, np.floating) else v) for k, v in row.items()}


def chance_threshold(n_test: int, n_classes: int, alpha: float = 0.05) -> float:
    """Accuracy a test set of this size needs to beat chance (binomial, Combrisson and Jerbi)."""
    return float(binom.ppf(1 - alpha, n_test, 1 / n_classes) / n_test)
