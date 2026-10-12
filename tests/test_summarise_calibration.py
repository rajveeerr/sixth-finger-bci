import importlib.util

import numpy as np
import pandas as pd
import pytest

from sixthfinger.config import load_data_config
from sixthfinger.paths import get_paths

K = [0, 1, 2, 3, 5, 10, 20]


@pytest.fixture(scope="module")
def cal():
    path = get_paths().root / "scripts" / "summarise_calibration.py"
    spec = importlib.util.spec_from_file_location("summarise_calibration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scores(gain: float, ah_gain: float, n_subjects=22, seed=0) -> pd.DataFrame:
    """Fold rows for both scenarios: rct_tslr = ts_lr + gain at small k, equal at k = all."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_subjects):
        s = f"sub-{i + 1:02d}"
        base = rng.uniform(0.45, 0.6)
        for scenario in ("S1_new_user", "S2_new_command"):
            for task in ("T2_rest_ah_sf", "T3_sf_vs_rest"):
                for k in K:
                    draws = ["0"] if k in (0, 20) else [*map(str, range(10)), "chrono"]
                    for d in draws:
                        noise = rng.normal(0, 0.01)
                        level = base + 0.02 * np.log1p(k)
                        rows += [
                            dict(scenario=scenario, task=task, session="pre", method="ts_lr",
                                 subject=s, k=k, draw=d,
                                 bal_acc=np.nan if k == 0 else level + noise),
                            dict(scenario=scenario, task=task, session="pre", method="rct_tslr",
                                 subject=s, k=k, draw=d,
                                 bal_acc=level + (gain if k < 20 else 0) + noise),
                        ]  # fmt: skip
                if scenario == "S2_new_command" and task == "T3_sf_vs_rest":
                    for k in K:
                        level = base + 0.02 * np.log1p(k) + gain - ah_gain
                        rows.append(dict(scenario=scenario, task=task, session="pre",
                                         method="ah_proxy", subject=s, k=k, draw="0",
                                         bal_acc=level))  # fmt: skip
    return pd.DataFrame(rows).assign(experiment="x", fold=0)


def _row(conf, hyp, population="all", basis="random"):
    return conf[(conf.hypothesis == hyp) & (conf.population == population)
                & (conf.draw_basis == basis) & (conf.role == "confirmatory")].iloc[0]  # fmt: skip


def test_a_clear_transfer_advantage_supports_h2a_h2b_h3(cal):
    values = cal.subject_values(_scores(gain=0.05, ah_gain=0.04))
    conf = cal.confirmatory(values, load_data_config(), ["sub-01", "sub-03"])
    assert _row(conf, "H2a").category == "supported"
    assert _row(conf, "H2a").n == 22 and _row(conf, "H2a", "without_dev").n == 20
    assert _row(conf, "H2b").category == "supported"  # advantage at 5, none at all
    assert _row(conf, "H3a").family_category == "supported"
    assert _row(conf, "H3c_k2").family_category == "supported"
    assert _row(conf, "H2a", basis="chrono").category == "supported"


def test_no_advantage_is_inconclusive_and_a_disadvantage_contrary(cal):
    values = cal.subject_values(_scores(gain=0.0, ah_gain=0.0, seed=1))
    conf = cal.confirmatory(values, load_data_config(), ["sub-01", "sub-03"])
    assert _row(conf, "H2a").category == "inconclusive"
    assert _row(conf, "H3c_k5").family_category == "inconclusive"
    worse = cal.subject_values(_scores(gain=-0.05, ah_gain=0.0, seed=2))
    conf = cal.confirmatory(worse, load_data_config(), ["sub-01", "sub-03"])
    assert _row(conf, "H2a").category == "contrary"
    assert _row(conf, "H3a").family_category == "contrary"


def test_alc_uses_only_the_k_both_methods_define(cal):
    values = cal.subject_values(_scores(gain=0.05, ah_gain=0.0))
    alcs = cal.pair_alcs(values, ("rct_tslr", "ts_lr"), "S1_new_user", "T2_rest_ah_sf", "pre",
                         "bal_acc")  # fmt: skip
    assert set(alcs.k_used) == {"1,2,3,5,10"}  # k = 0 is undefined for ts_lr, not in K anyway


def test_k_star_is_censored_when_never_reached(cal):
    values = cal.subject_values(_scores(gain=0.0, ah_gain=0.0))
    eff = cal.efficiency(values)
    t2 = eff[(eff.task == "T2_rest_ah_sf") & (eff.method == "ts_lr")]
    assert t2.censored_70.all() and t2.k_star_70.isna().all()  # levels stay below 0.70


def test_minutes_follow_the_protocol(cal):
    assert cal.minutes("S1_new_user", 10, transfer=False) == pytest.approx(2 * 10 * 14 / 60)
    assert cal.minutes("S2_new_command", 5, transfer=False) == pytest.approx(5 * 14 / 60)
    assert cal.minutes("S1_new_user", 0, transfer=True) == pytest.approx(40 * 7 / 60)


def test_the_no_signal_check_flags_a_method_far_from_chance(cal, tmp_path):
    rows = [dict(task="T2_rest_ah_sf", method="ok", bal_acc=0.35),
            dict(task="T2_rest_ah_sf", method="leaky", bal_acc=0.60),
            dict(task="T3_sf_vs_rest", method="ok", bal_acc=0.55)]  # fmt: skip
    (tmp_path / "rq2_nosignal").mkdir()
    pd.DataFrame(rows).to_parquet(tmp_path / "rq2_nosignal" / "scores.parquet")
    out = cal.nosignal(tmp_path).set_index(["task", "method"]).passes
    assert out[("T2_rest_ah_sf", "ok")] and not out[("T2_rest_ah_sf", "leaky")]
    assert out[("T3_sf_vs_rest", "ok")]


def test_trials_saved_counts_every_subject_once(cal):
    values = cal.subject_values(_scores(gain=0.05, ah_gain=0.0))
    eff = cal.efficiency(values)
    for task, thr in (("T2_rest_ah_sf", 60), ("T3_sf_vs_rest", 70)):
        r = cal.trials_saved(eff, ("rct_tslr", "ts_lr"), "S1_new_user", task, "pre", thr)
        total = r["n_both_reach"] + r["n_only_first"] + r["n_only_second"] + r["n_neither"]
        assert total == 22
