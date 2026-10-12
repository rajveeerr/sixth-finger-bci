import math

import numpy as np
import pandas as pd
import pytest

from sixthfinger.evaluation import pseudo_online as po


def test_the_gate_is_the_servers_own_class():
    gate = po.load_gate_class()
    assert gate.__module__ == "sixthfinger_server_gate"
    g = gate()
    assert (g.alpha, g.threshold, g.dwell, g.release) == (0.3, 0.6, 2, 0.45)  # protocol §6b


def test_windows_step_by_the_stride_and_skip_a_boundary():
    ends = po.window_ends(n_times=3000, n_window=1000, stride=125, boundaries=np.array([]))
    assert ends[0] == 1000 and ends[-1] == 3000 and np.all(np.diff(ends) == 125)
    cut = po.window_ends(3000, 1000, 125, boundaries=np.array([1500]))
    # A window [e - 1000, e) is split when e - 1000 < 1500 < e: ends 1625 to 2375 go.
    assert not set(cut) & set(range(1625, 2500, 125)) and 1500 in cut and 2500 in cut


def test_periods_follow_the_event_codes():
    p = po.periods(["1", "boundary", "3", "1", "2"], np.array([0, 10, 2000, 3500, 5500]), 250,
                   n_times=6500)  # fmt: skip
    assert p.kind.tolist() == ["rest", "SF", "rest", "AH"]
    assert p.stop.tolist() == [1750, 3500, 5250, 6500]  # 7 s, 6 s, 7 s, clipped at the end


def test_an_activation_is_a_change_from_idle_to_a_command():
    active = np.array([0, 0, 2, 2, 0, 1, 2, 0])
    ends = np.arange(8) * 125 + 1000
    acts = po.activations(active, ends)
    assert acts.command.tolist() == [2, 1] and acts["sample"].tolist() == [1250, 1625]
    assert acts.attrs["command_switches"] == 1  # 1 -> 2 without IDLE is not counted


def test_the_metrics_count_detections_false_activations_and_latency():
    sf = 250
    per = pd.DataFrame(dict(kind=["rest", "SF", "rest", "AH", "rest", "SF"],
                            start=[0, 2000, 3500, 5500, 7000, 9000],
                            stop=[1750, 3500, 5250, 7000, 8750, 10500]))  # fmt: skip
    acts = pd.DataFrame({"sample": [500, 2500, 6000, 6250], "command": [1, 2, 2, 1]})
    m = po.subject_metrics([po.RunReplay(per, acts, sf)])
    assert m["sf_detection_rate"] == 0.5  # the second SF period has none
    assert m["ah_detection_rate"] == 1.0 and m["ah_as_sf_rate"] == 1.0
    assert m["false_activations"] == 1 and m["false_per_minute"] == pytest.approx(1 / (21 / 60))
    assert m["sf_latency_s"] == pytest.approx(2.0) and m["ah_latency_s"] == pytest.approx(3.0)
    # Correct outcomes: 1 SF period detected + 2 quiet rest periods, of 2 SF + 3 rest.
    assert m["itr_p_correct"] == pytest.approx(3 / 5)


def test_itr_is_wolpaw_and_zero_at_chance():
    p = 0.8
    b = 1 + p * math.log2(p) + (1 - p) * math.log2(1 - p)
    assert po.itr_bits_per_minute(p) == pytest.approx(b * 60 / 14)
    assert po.itr_bits_per_minute(0.5) == 0.0 and po.itr_bits_per_minute(1.0) == pytest.approx(
        60 / 14
    )


def test_the_gate_is_reset_for_every_run():
    gate = po.load_gate_class()
    sure_sf = np.tile([0.0, 0.0, 1.0], (6, 1))
    first = po.replay(sure_sf, gate)
    assert first[0] == 0 and first[-1] == 2  # dwell and smoothing delay the first command
    np.testing.assert_array_equal(po.replay(sure_sf, gate), first)


def test_the_one_switch_view_merges_both_imagery_classes():
    proba = np.array([[0.5, 0.3, 0.2], [0.1, 0.1, 0.8]])
    np.testing.assert_allclose(po.any_imagery(proba), [[0.5, 0.5], [0.1, 0.9]])
    per = pd.DataFrame(dict(kind=["rest", "AH", "rest", "SF"], start=[0, 2000, 3500, 5500],
                            stop=[1750, 3500, 5250, 7000]))  # fmt: skip
    acts = pd.DataFrame({"sample": [2600, 4000], "command": [1, 1]})
    m = po.switch_metrics([po.RunReplay(per, acts, 250)])
    assert m["imagery_detection_rate"] == 0.5 and m["latency_s"] == pytest.approx(2.4)
    assert m["false_per_minute"] == pytest.approx(1 / (14 / 60))


def _run_with_truth(sf=250):
    """A run of two trials (SF then AH); channel 0 carries the true class as a value."""
    codes = ["1", "3", "1", "2"]
    samples = np.array([0, 2125, 4000, 6125])
    data = np.zeros((2, 8000))
    data[0, 2125 : 2125 + 6 * sf] = 2.0  # SF imagery
    data[0, 6125 : 6125 + 6 * sf] = 1.0  # AH imagery
    return data, codes, samples, sf


def _oracle(windows):
    """Probabilities in class order [REST, AH, SF] from the last sample of each window."""
    last = windows[:, 0, -1].round().astype(int)
    return np.eye(3)[last]


def test_a_perfect_decoder_detects_every_period_with_no_false_activation():
    data, codes, samples, sf = _run_with_truth()
    run, tl = po.replay_run(
        _oracle, data, codes, samples, sf, n_window=250, gate_cls=po.load_gate_class()
    )
    m = po.subject_metrics([run])
    assert m["sf_detection_rate"] == 1.0 and m["ah_detection_rate"] == 1.0
    assert m["ah_as_sf_rate"] == 0.0 and m["false_activations"] == 0
    assert set(tl.columns) >= {"t", "p_rest", "p_ah", "p_sf", "active"}
    # Reversed or shuffled columns would flex during rest and miss the SF period above.
    assert tl.p_sf.max() == 1 and tl.p_ah.max() == 1


def test_the_replayed_runs_are_the_test_runs_and_never_the_pool():
    assert po.replayed_runs(["03", "04"], ["01", "02"]) == [3, 4]
    with pytest.raises(ValueError, match="overlap"):
        po.replayed_runs(["02", "03"], ["01", "02"])


def test_latency_is_the_median_over_detected_periods():
    per = pd.DataFrame(
        dict(kind=["SF", "SF", "SF"], start=[0, 2000, 4000], stop=[1500, 3500, 5500])
    )
    acts = pd.DataFrame({"sample": [250, 2500, 5000], "command": [2, 2, 2]})  # 1, 2 and 4 s
    m = po.subject_metrics([po.RunReplay(per, acts, 250)])
    assert m["sf_latency_s"] == pytest.approx(2.0)  # the mean would be 2.33
