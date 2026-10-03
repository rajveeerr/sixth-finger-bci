import json

import numpy as np
import pytest

from sixthfinger.evaluation.metrics import chance_threshold, score


def _onehot(pred, classes):
    return np.eye(len(classes))[[classes.index(p) for p in pred]]


def test_perfect_predictions_score_one():
    classes = [0, 1, 2]
    y = np.array([0, 1, 2, 2, 1, 0])
    row = score(y, _onehot(y, classes), classes)
    for key in ("bal_acc", "acc", "f1_macro", "kappa", "sf_recall", "sf_precision", "auc_sf"):
        assert row[key] == pytest.approx(1.0)
    assert json.loads(row["confusion"]) == [[2, 0, 0], [0, 2, 0], [0, 0, 2]]


@pytest.mark.parametrize("classes", [[1, 2], [0, 1, 2]])
def test_constant_predictor_is_at_chance(classes):
    y = np.repeat(classes, 10)
    proba = np.tile(np.eye(len(classes))[0], (len(y), 1))
    assert score(y, proba, classes)["bal_acc"] == pytest.approx(1 / len(classes))


def test_sf_metrics_missing_when_task_has_no_sf():
    y = np.array([0, 1, 0, 1])
    row = score(y, _onehot(y, [0, 1]), [0, 1])
    assert np.isnan(row["sf_recall"]) and np.isnan(row["auc_sf"])


def test_chance_threshold_matches_the_binomial_table():
    assert chance_threshold(80, 2) == pytest.approx(0.5875)
    assert chance_threshold(80, 2) > chance_threshold(800, 2) > 0.5
