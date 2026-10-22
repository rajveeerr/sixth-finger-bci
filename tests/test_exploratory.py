import numpy as np
import pandas as pd
import pytest
import torch

from sixthfinger.evaluation import exploratory as ex

REST, AH, SF = 0, 1, 2


def _decisions(conf, correct, y):
    """conf, correct and labels as the gate sees them for a two-class task."""
    return np.asarray(conf, float), np.asarray(correct, bool), ex.class_weights(np.asarray(y))


def test_acting_on_every_window_gives_balanced_accuracy():
    y = np.array([0, 0, 0, 0, 0, 0, 2, 2])
    correct = np.array([1, 1, 1, 1, 1, 1, 0, 1], bool)
    acc_w, acc_plain, share = ex.acting(correct, ex.class_weights(y), np.ones(8, bool))
    assert acc_w == pytest.approx((1.0 + 0.5) / 2)  # mean of the two class recalls
    assert acc_plain == pytest.approx(7 / 8) and share == 1.0


def test_threshold_is_the_lowest_that_reaches_the_target():
    # Sorted by confidence: right, right, wrong, right, right, right, right, then wrong. Acting
    # on the top 3 or 4 falls below 80 %, the top 5 to 7 reach it again: the lowest wins.
    conf = [0.99, 0.95, 0.90, 0.85, 0.80, 0.70, 0.65, 0.60, 0.55, 0.52]
    correct = [1, 1, 0, 1, 1, 1, 1, 0, 0, 0]
    y = [0, 2] * 5
    c, ok, w = _decisions(conf, correct, y)
    picked = ex.pick_threshold(c, ok, w, target=0.8, min_share=0.1)
    assert picked["reached_target"]
    assert picked["threshold"] == 0.65  # acts on 7 windows, 6 right
    assert picked["inner_share"] == pytest.approx(0.7)


def test_threshold_never_acts_on_less_than_the_minimum_share():
    # Only the single most confident window is right: 100 % on 5 % of the windows is not allowed.
    conf = np.linspace(1.0, 0.5, 20)
    correct = np.zeros(20, bool)
    correct[0] = True
    c, ok, w = _decisions(conf, correct, [0, 2] * 10)
    picked = ex.pick_threshold(c, ok, w, target=0.9, min_share=0.1)
    assert picked["inner_share"] >= 0.1 and not picked["reached_target"]


def test_without_the_target_the_best_accuracy_wins_and_a_tie_takes_the_lower():
    conf = [0.9, 0.8, 0.7, 0.6]
    c, ok, w = _decisions(conf, [1, 0, 1, 0], [0, 2, 0, 2])
    picked = ex.pick_threshold(c, ok, w, target=0.99, min_share=0.5)
    # Allowed: 0.8 (1 of 2 right), 0.7 (2 of 3), 0.6 (2 of 4); class-weighted 0.7 is best.
    assert picked["threshold"] == 0.7 and not picked["reached_target"]
    c, ok, w = _decisions(conf, [1, 0, 0, 1], [0, 2, 0, 2])
    tie = ex.pick_threshold(c, ok, w, target=0.99, min_share=0.5)
    assert tie["threshold"] == 0.6 and tie["inner_acc"] == pytest.approx(0.5)  # 0.8 ties it


def test_firing_rates_count_the_command_and_the_gate_per_class():
    # A rest-vs-SF command shown hand-imagery windows: how often does it say "sixth finger"?
    P_ah = np.array([[0.1, 0.9], [0.3, 0.7], [0.8, 0.2], [0.45, 0.55]])
    conf, pred, _ = ex.decisions(np.full(4, AH), P_ah, [REST, SF])
    fire, gated = ex.fire_rates(pred, conf, threshold=0.65, command=SF)
    assert fire == 0.75  # three of four windows decided as SF
    assert gated == 0.5  # of those, 0.9 and 0.7 clear the threshold; 0.55 does not
    rest = np.array([[0.9, 0.1], [0.6, 0.4]])
    conf, pred, _ = ex.decisions(np.full(2, REST), rest, [REST, SF])
    assert ex.fire_rates(pred, conf, 0.65, SF) == (0.0, 0.0)


def test_coverage_acts_on_the_most_confident_share_rounded_up():
    conf = np.array([0.6, 0.9, 0.7, 0.8, 0.95])
    correct = np.array([0, 1, 0, 1, 0], bool)
    y = np.array([0, 2, 0, 2, 0])
    curve = {s: a for s, a, _ in ex.coverage(conf, correct, ex.class_weights(y), [0.2, 0.3])}
    assert curve[0.2] == 0.0  # the top window (0.95) is wrong
    # 30 % of 5 rounds up to 2 windows: 0.95 (wrong, rest) and 0.9 (right, SF), weighted 1/3, 1/2
    assert curve[0.3] == pytest.approx(0.5 / (1 / 3 + 0.5))


class _Net(torch.nn.Module):
    def __init__(self, logits):
        super().__init__()
        self.logits = torch.tensor(logits, dtype=torch.float32)

    def forward(self, x):
        return self.logits[: len(x)]


class _Method:
    """Stands in for a fitted eegnet_ea_ft: identity alignment, fixed logits."""

    def __init__(self, logits, classes):
        self.R, self.classes = np.eye(2, dtype=np.float32), classes
        self.clf = type("C", (), {"module_": _Net(logits)})()

    def _x(self, X):
        return np.asarray(X, np.float32)

    def predict_proba(self, X):
        p = torch.softmax(self.clf.module_(X), dim=1).numpy()[:, self.classes]
        return p / p.sum(axis=1, keepdims=True)


def test_task_probabilities_survive_a_window_the_network_puts_on_rest():
    # Window 2 puts all float32 mass on REST: softmax-then-renormalise divides 0 by 0 there.
    logits = [[0.0, 1.0, 2.0], [200.0, 0.0, 1.0]]
    m = _Method(logits, classes=[1, 2])
    X = np.zeros((2, 2, 4), np.float32)
    proba, n_nan = ex.task_proba(m, X, [1, 2])
    assert n_nan == 1 and np.isfinite(proba).all()
    expected = torch.softmax(torch.tensor([[1.0, 2.0], [0.0, 1.0]], dtype=torch.float64), 1)
    assert np.allclose(proba, expected.numpy())


def test_the_crop_mean_averages_the_crops_a_window_has():
    class Mean:
        def predict_proba(self, X):
            v = X.mean(axis=(1, 2))
            return np.stack([1 - v, v], axis=1)

    crops = {0.0: (np.array([0, 1, 2]), np.full((3, 1, 2), 0.2)),
             0.5: (np.array([0, 2]), np.full((2, 1, 2), 0.6))}  # fmt: skip
    p = ex.crop_mean(Mean(), crops, rows=np.array([1, 2]), n_rows=3, chans=None)
    assert p[:, 1] == pytest.approx([0.2, 0.4])  # window 1 lost its second crop at a cut


def test_paired_row_leaves_the_development_patients_out_of_the_sensitivity_row():
    subjects = ["sub-01", "sub-02", "sub-03", "sub-04"]
    a = pd.Series([0.9, 0.6, 0.9, 0.7], index=subjects)
    b = pd.Series([0.5, 0.5, 0.5, 0.5], index=subjects)
    row = ex.paired_row("x", a, b, "a", "b")
    assert row["n"] == 4 and row["n_without_dev"] == 2
    assert row["diff_points"] == pytest.approx(27.5)
    assert row["diff_points_without_dev"] == pytest.approx(15.0)
    assert (row["better"], row["worse"], row["tied"]) == (4, 0, 0)


def test_table_diff_ignores_provenance_and_counts_changed_cells():
    old = pd.DataFrame({"subject": ["a", "b"], "bal_acc": [0.5, 0.6], "git_sha": ["x", "x"]})
    same = old.assign(git_sha="y", source_commit="z")
    assert ex.table_diff(same, old)["identical"]
    moved = same.assign(bal_acc=[0.5, 0.65])
    res = ex.table_diff(moved, old)
    assert res["cells_differing"] == 1 and res["max_abs_diff"] == pytest.approx(0.05)
    assert ex.json_diff({"k": 1.0, "git_sha": "y"}, {"renamed": 1.0, "git_sha": "x"})["identical"]
