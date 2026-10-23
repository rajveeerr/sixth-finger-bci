"""The paper's numbers: valid LaTeX names, copied from the results unchanged, kept current (P13)."""

import importlib.util
import re
import sys

import pandas as pd
import pytest

from sixthfinger.paths import get_paths

ROOT = get_paths().root
GENERATED = ROOT / "paper" / "generated"


@pytest.fixture(scope="module")
def module():
    path = ROOT / "scripts" / "make_paper_numbers.py"
    spec = importlib.util.spec_from_file_location("make_paper_numbers", path)
    module = importlib.util.module_from_spec(spec)
    # Its dataclasses look their module up while being defined.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def nums(module):
    return module.build(ROOT)


def summary(name: str) -> pd.DataFrame:
    return pd.read_csv(ROOT / "results" / "summary" / name)


def row(df: pd.DataFrame, **where) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    for column, value in where.items():
        mask &= df[column] == value
    assert mask.sum() == 1, where
    return df[mask].iloc[0]


def test_macro_names_are_letters_only_and_unique(module, nums):
    defined = re.findall(r"\\newcommand\{\\([^}]*)\}", (GENERATED / "numbers.tex").read_text())
    assert all(re.fullmatch(r"[A-Za-z]+", name) for name in defined)
    assert len(defined) == len(set(defined))
    assert set(nums.entries) <= set(defined)
    assert all(module.OWNED.fullmatch("\\" + name) for name in nums.entries)


def test_values_are_the_results_files_values(nums):
    rq1 = summary("rq1_table.csv")
    curves = summary("calib_curves.csv")
    s1 = {"scenario": "S1_new_user", "task": "T2_rest_ah_sf", "session": "pre", "population": "all"}
    ex4 = summary("ex4_sf_command_table.csv")
    ex5 = summary("ex5_live_switch_table.csv")
    expected = {
        "rqOneCspLdaCvLeakfreeMean": 100
        * row(
            rq1,
            task="T1_ah_vs_sf",
            method="csp_lda",
            protocol="cv_leakfree",
            session="pre",
            population="all",
        )["mean"],
        "rqOneHOneDiff": row(summary("rq1_stats.csv"), test_id="H1").mean_diff,
        "rqTwoRestAhSfRctTslrKOneMean": 100 * row(curves, **s1, method="rct_tslr", k=1)["mean"],
        "rqTwoRestAhSfTsLrKTenMean": 100 * row(curves, **s1, method="ts_lr", k=10)["mean"],
        "rqTwoMinutesKTen": row(curves, **s1, method="ts_lr", k=10).minutes,
        "rqTwoAdvantageKOneDiff": row(summary("calib_h2a_per_k.csv"), k=1).mean_diff,
        "exOneArmBVsTsLrArmMean": 100
        * row(summary("ex1_transfer_ah_sf_paired.csv"), comparison="B_vs_ts_lr").arm_mean,
        "exFourTsLrCentralMean": 100 * row(ex4, section="part1", row="ts_lr_c14")["mean"],
        "exFourTsLrCentralSureMean": 100
        * row(ex4, section="arm_R", row="R (ts_lr_c14), accuracy when acting")["mean"],
        "exFourTsLrCentralFiresAhMean": 100
        * row(ex4, section="part2_fires", row="ts_lr_c14 fire_ah")["mean"],
        "exFiveMoveDetectMean": 100
        * row(ex5, arm="M14", population="all", metric="imagery_detection_rate")["mean"],
        "rqFiveMumtazBpLrInflation": row(
            summary("rq5_stats.csv"), dataset="mumtaz", pipeline="bp_lr"
        ).inflation_points,
        "rqFourLaterPostUnchangedMean": 100
        * row(
            summary("rq4_longitudinal_table.csv"),
            session="post",
            arm="pre_unchanged",
            population="all",
        )["mean"],
    }
    for name, value in expected.items():
        assert nums.entries[name].plain == f"{value:.1f}", name
    confirmatory = row(
        summary("calib_confirmatory.csv"),
        hypothesis="H2a",
        role="confirmatory",
        session="pre",
        population="all",
        draw_basis="random",
    )
    assert nums.entries["rqTwoHTwoAMedianDiff"].plain == f"{confirmatory.median_diff:.3f}"
    move = row(ex5, arm="M14", population="all", metric="false_per_minute")
    assert nums.entries["exFiveMoveFalsePerMinMean"].plain == f"{move['mean']:.2f}"
    windows = pd.read_csv(ROOT / "results" / "audit" / "epoch_counts.csv")
    total = windows[["rest", "affected_hand", "sixth_finger"]].to_numpy().sum()
    assert nums.entries["nWindows"].plain == str(total)
    assert nums.entries["nWindows"].kind == "count"


def test_group_numbers_are_the_summaries_values(nums):
    """The numbers each analysis's summary step states for the text, copied unchanged."""
    import json

    erd = row(summary("eda_erd_summary.csv"), session="pre", band="mu", channel="C3")
    leak = row(summary("rq1_stats.csv"), test_id="H1")
    recall = row(
        summary("dl_class_recall.csv"),
        task="T3_sf_vs_rest",
        method="eegnet_scratch",
        protocol="chrono",
        **{"class": "rest"},
    )
    pool = row(
        summary("calib_pair_whole_pool.csv"),
        scenario="S1_new_user",
        task="T2_rest_ah_sf",
        session="pre",
    )
    cue = row(
        summary("rq4_visual_cue_paired.csv"),
        task="T3_sf_vs_rest",
        comparison="parieto_occipital_5 vs central_14",
    )
    shuffled = row(summary("rq5_null_summary.csv"), protocol="segment_cv")
    dl = json.loads((ROOT / "results" / "summary" / "dl_summary.json").read_text())
    expected = {
        "edaErdMuCThreeAhMean": erd.mean_affected_hand,
        "rqOneHOneDiffMin": leak.min_diff,
        "rqOneHOneDiffMax": leak.max_diff,
        "dlSfRestChronoEegnetScratchRecallRest": 100 * recall.mean_recall,
        "dlEegnetScratchSeedSdMean": dl["seed SD per patient, task and protocol (points)"]["mean"],
        "rqTwoRestAhSfTsLrMinusRctTslrKAllDiff": -pool.mean_diff_points,
        "rqFourCueSfRestCentralMinusParietoOccipitalDiff": -cue.diff_points,
        "rqFiveShuffledSegmentCvMean": 100 * shuffled["mean"],
    }
    for name, value in expected.items():
        assert nums.entries[name].plain == f"{value:.1f}".replace("-", "\N{MINUS SIGN}"), name
    assert nums.entries["edaErdMuCThreeSfMoreNegative"].plain == str(erd.n_sf_more_negative)
    trials = pd.read_csv(ROOT / "results" / "audit" / "epoch_trials.csv")
    assert nums.entries["nTrials"].plain == str(trials.trials.sum())
    assert nums.entries["nTrials"].kind == "count"


def test_review_numbers_are_the_summaries_values(nums):
    """The numbers added in answer to the paper's review, copied from their summaries."""
    leakfree = row(
        summary("rq1_table.csv"),
        task="T1_ah_vs_sf",
        method="csp_lda",
        protocol="cv_leakfree",
        session="pre",
        population="all",
    )
    gap = row(summary("rq1_runwise_gap.csv"), session="pre", comparison="paper_replica - loro")
    minutes = row(summary("calib_minutes.csv"), session="pre", scenario="S1_new_user", k=20)
    h2b = row(
        summary("calib_confirmatory.csv"),
        hypothesis="H2b",
        role="confirmatory",
        session="pre",
        population="all",
        draw_basis="random",
    )
    expected = {
        "rqOneCspLdaCvLeakfreeMin": 100 * leakfree.min_bal_acc,
        "rqOneCspLdaPaperReplicaMinusLoroDiff": gap["mean"],
        "rqTwoMinutesRecordedKAll": minutes.minutes_recorded,
        "rqTwoTrialSecondsRecorded": minutes.trial_s_recorded,
        "rqTwoHTwoBPointsDiff": 100 * h2b.mean_diff,
    }
    for name, value in expected.items():
        assert nums.entries[name].plain == f"{value:.1f}", name
    below = str(leakfree.n_below_chance_level)
    assert nums.entries["rqOneCspLdaCvLeakfreeNBelowChance"].plain == below


def test_demo_timing_and_weights_are_the_files_values(nums):
    import json

    def read(name):
        return json.loads((ROOT / "results" / "summary" / name).read_text())

    timing, weights = read("demo_inference_timing.json"), read("eegnet_weights.json")
    assert nums.entries["demoInferenceMedianMs"].plain == f"{timing['latency_ms']['median']:.2f}"
    assert nums.entries["demoInferenceIqrHiMs"].plain == f"{timing['latency_ms']['q3']:.2f}"
    assert nums.entries["demoInferenceN"].plain == str(timing["n"])
    assert nums.entries["demoInferenceMachine"].plain == timing["machine"]["cpu"]
    assert nums.entries["dlEegnetWeights"].plain == str(weights["study_model"]["trainable"])
    assert weights["deployed_onnx"]["numbers"] == int(nums.entries["demoParameters"].plain)


def test_formats(module):
    assert module.pct(0.584693).tex == "58.5"
    assert module.pct(-0.0123).tex == r"\ensuremath{-1.2}"
    assert module.sig(2.38419e-07).tex == r"\ensuremath{2.4\times10^{-7}}"
    assert module.sig(0.0127273).tex == "0.013"
    assert module.sig(1.0).tex == "1.0"
    assert module.integer(35778).tex == r"35\,778"
    assert module.integer(9615).tex == "9615"
    assert module.word("eegnet_scratch").tex == r"eegnet\_scratch"


def test_a_macro_used_but_not_generated_prints_as_tbd(module, nums, tmp_path):
    section = tmp_path / "results.tex"
    section.write_text(
        r"We reached \rqTwoNotAResult\,\% and \rqOneCspLdaCvLeakfreeMean\,\%; $a \nRightarrow b$."
    )
    used, placeholders = module.used_macros([section])
    assert used == {"rqTwoNotAResult", "rqOneCspLdaCvLeakfreeMean"}
    assert not placeholders
    missing = module.missing_macros(nums, used)
    assert missing["rqTwoNotAResult"] == "rqTwoNotAResult"
    tex = module.render_tex(nums, missing, placeholders)
    assert r"\newcommand{\rqTwoNotAResult}{\TBD{rqTwoNotAResult}}" in tex
    assert module.TBD in tex


def test_committed_numbers_are_current(module, nums):
    used, placeholders = module.used_macros(module.tex_sources(ROOT))
    missing = module.missing_macros(nums, used)
    hint = "run: uv run python scripts/make_paper_numbers.py"
    tex = module.render_tex(nums, missing, placeholders)
    assert tex == (GENERATED / "numbers.tex").read_text(), hint
    assert module.render_index(nums, missing) == (GENERATED / "numbers-index.md").read_text(), hint
