"""The numbers behind the demo page's explanatory figures (web/src/explain/data.json).

uv run python scripts/make_web_explain_data.py
uv run python scripts/make_web_explain_data.py --facts-only   # results/summary/demo_page.json

Every value is read from a results file named in the output's "sources", so the page
never carries a number typed by hand. Run again whenever those summaries change. The two
numbers the page works out from the demo bundle itself, the model's size and its two readings,
are also written to results/summary/demo_page.json for the paper and the report.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import mne
import numpy as np
import onnx
import pandas as pd

from sixthfinger.data.channels import CHANNELS_40
from sixthfinger.paths import get_paths

# The demo chart's channels (the bundle's display_channels) and the sensorimotor strip.
DISPLAY = ["FC3", "C3", "CP3", "Cz", "FC4", "C4", "CP4"]
MOTOR = set(DISPLAY) | {"FC1", "FCz", "FC2", "C5", "C1", "C2", "C6", "CP1", "CPz", "CP2"}
TASKS = [
    ("T3_sf_vs_rest", "Rest or sixth finger", 0.5),
    ("T2_rest_ah_sf", "All three", 1 / 3),
    ("T1_ah_vs_sf", "Hand or sixth finger", 0.5),
]
SECONDS_PER_TRIAL = 14


def r(x: float, n: int = 4) -> float:
    return round(float(x), n)


def electrodes() -> list[dict]:
    """Top view, nose up: azimuthal equidistant projection (as make_montage_figure)."""
    pos = mne.channels.make_standard_montage("colin27_1005").get_positions()["ch_pos"]
    out = []
    for name in CHANNELS_40:
        x, y, z = pos[name] / np.linalg.norm(pos[name])
        theta = np.arccos(np.clip(z, -1, 1))
        phi = np.arctan2(y, x)
        px, py = theta * np.cos(phi), theta * np.sin(phi)
        out.append(
            {
                "name": name,
                "x": r(px / (np.pi / 2), 4),  # 1.0 = the head's rim
                "y": r(py / (np.pi / 2), 4),
                "shown": name in DISPLAY,
                "motor": name in MOTOR,
            }
        )
    return out


OUT = ("web", "src", "explain", "data.json")
OUT_HEAD = ("web", "src", "explain", "head.json")
OUT_FACTS = ("results", "summary", "demo_page.json")


def head_model() -> dict:
    """MNE's template adult head (fsaverage's outer skin, bundled with MNE) in millimetres,
    with the 40 electrodes of the colin27 10-05 montage, which is defined on the same head."""
    folder = Path(mne.__file__).parent / "data" / "fsaverage"
    surf = mne.read_bem_surfaces(folder / "fsaverage-head.fif", verbose=False)[0]
    pos = mne.channels.make_standard_montage("colin27_1005").get_positions()
    assert pos["coord_frame"] == "mri", pos["coord_frame"]
    return {
        "source": "mne/data/fsaverage/fsaverage-head.fif, colin27_1005 montage (MRI frame, mm)",
        "vertices": [[r(v, 1) for v in p] for p in surf["rr"] * 1000],
        "faces": surf["tris"].tolist(),
        "electrodes": {name: [r(v, 1) for v in pos["ch_pos"][name] * 1000] for name in CHANNELS_40},
    }


def model_parameters() -> int:
    """The numbers in the demo's model as the browser runs it (the exported ONNX graph)."""
    model = onnx.load(get_paths().root / "web" / "public" / "demo" / "model.onnx")
    return int(sum(np.prod(t.dims) for t in model.graph.initializer))


def balanced(truth: list, guess: list) -> float:
    """Each class's share read right, averaged over the classes (as balanced accuracy)."""
    classes = sorted(set(truth))
    hits = [np.mean([g == c for t, g in zip(truth, guess, strict=True) if t == c]) for c in classes]
    return float(np.mean(hits))


def demo_readings() -> dict:
    """The demo's two readings, scored on its stored held-out predictions (predictions.json,
    made by the same model as model.onnx): move or rest, rest's chance against the hand's
    and the sixth finger's added, on every rest and imagery window; and the hand-or-finger
    guess, the likelier of those two, on the imagery windows."""
    demo = get_paths().root / "web" / "public" / "demo"
    manifest = json.loads((demo / "manifest.json").read_text())
    stored = json.loads((demo / "predictions.json").read_text())
    if stored["model_sha256"] != manifest["model"]["sha256"]:
        raise ValueError("predictions.json was made by another model than the manifest's")
    names = [c["name"] for c in manifest["classes"]]
    rest, hand, finger = (names.index(n) for n in ("rest", "affected_hand", "sixth_finger"))
    cue = {t["index"]: names[t["label"]] for t in manifest["trials"]}
    move_truth, move_read, which_truth, which_read = [], [], [], []
    for item in stored["items"]:
        p = item["probs"]
        imagery = item["window"] == "imagery"
        move_truth.append(imagery)
        move_read.append(p[hand] + p[finger] > p[rest])
        if imagery:
            which_truth.append(cue[item["trial"]])
            which_read.append(names[hand] if p[hand] >= p[finger] else names[finger])
    return {
        "move_rest": {
            "acc": r(balanced(move_truth, move_read)),
            "right": int(sum(t == g for t, g in zip(move_truth, move_read, strict=True))),
            "n": len(move_truth),
        },
        "hand_finger": {
            "acc": r(balanced(which_truth, which_read)),
            "right": int(sum(t == g for t, g in zip(which_truth, which_read, strict=True))),
            "n": len(which_truth),
        },
    }


def demo_facts() -> dict:
    """The page's numbers about the demo model that come from the bundle, not from results/."""
    return {
        "sources": ["web/public/demo/model.onnx", "web/public/demo/predictions.json"],
        "parameters": model_parameters(),
        **demo_readings(),
    }


def sixth_command(summary: Path) -> dict:
    """Question 3, the sixth finger as its own command (EX4): the headline switch (sixth finger
    or rest, `ts_lr` on the 14 central channels), the same switch acting only when sure (arm
    R), how often each kind of window turns it on, and hand or sixth finger with the best
    method (`eegnet_ea_ft`), on every window and acting only when sure."""
    table = pd.read_csv(summary / "ex4_sf_command_table.csv").set_index(["section", "row"])
    per_patient = pd.read_csv(summary / "ex4_sf_command_per_patient.csv").sort_values("subject")
    coverage = pd.read_csv(summary / "ex4_sf_command_coverage.csv")

    def patients(row: pd.Series, column: str) -> dict:
        return {
            "mean": r(row["mean"]),
            "ci": [r(row.ci_lo), r(row.ci_hi)],
            "values": [r(v) for v in per_patient[column]],
            "n": int(row.n),
            "n_ge_80": int(row.n_ge_80),
            "n_ge_90": int(row.n_ge_90),
        }

    switch = table.loc[("part1", "ts_lr_c14")]
    if str(switch.headline) != "True":
        raise ValueError("ts_lr_c14 is no longer EX4's headline arm")
    sure = table.loc[("arm_R", "R (ts_lr_c14), accuracy when acting")]
    which = table.loc[("part2_T1", "T1_ea_ft, all windows")]
    which_sure = table.loc[("part2_T1", "T1_ea_ft, accuracy when acting")]
    curve = coverage[(coverage.task == "T3_sf_vs_rest") & (coverage.arm == "ts_lr_c14")]
    curve = curve[pd.to_numeric(curve.share, errors="coerce").notna()]
    fires = {
        name: {
            "all": r(table.loc[("part2_fires", f"ts_lr_c14 fire_{kind}"), "mean"]),
            "sure": r(table.loc[("part2_fires", f"ts_lr_c14 fire_{kind}_gated"), "mean"]),
        }
        for name, kind in (("rest", "rest"), ("hand", "ah"), ("finger", "sf"))
    }
    return {
        "rest": {
            **patients(switch, "test_ts_lr_c14"),
            "all_sensors": r(table.loc[("part1", "ts_lr"), "mean"]),
        },
        "which": patients(which, "test_T1_ea_ft"),
        "sure": {
            "acc": r(sure["mean"]),
            "ci": [r(sure.ci_lo), r(sure.ci_hi)],
            "share": r(sure.share_mean),
            "n": int(sure.n),
            "n_ge_90": int(sure.n_ge_90),
            "no_decision": int(sure.n_patients_no_action),
        },
        "coverage": [
            {
                "share": r(float(c.share), 2),
                "acc": r(c.acc_when_acting),
                "ci": [r(c.ci_lo), r(c.ci_hi)],
            }
            for c in curve.sort_values("share", key=lambda s: s.astype(float)).itertuples()
        ],
        "fires": fires,
        "which_sure": {
            "acc": r(which_sure["mean"]),
            "share": r(which_sure.share_mean),
            "n": int(which_sure.n),
            "no_decision": int(which_sure.n_patients_no_action),
        },
    }


def central_switch(summary: Path) -> dict:
    """EX5: question 3's simpler model (`ts_lr` on the 14 central channels), learned as rest or
    any movement and played as if live like answer 4. The analysis's page rule, fixed before
    scoring, keeps `eegnet_scratch` as the answer unless this switch catches more and errs less;
    the page's copy is written for that outcome, so a different one stops the build."""
    checks = json.loads((summary / "ex5_live_switch_checks.json").read_text())
    shows = checks["page rule (settings page_rule)"]["page_shows"]
    if shows != "eegnet_scratch":
        raise ValueError(f"EX5's page rule now shows {shows}: answer 4 must be rewritten")
    t = pd.read_csv(summary / "ex5_live_switch_table.csv")
    t = t[(t.arm == "M14") & (t.population == "all")].set_index("metric")
    return {
        # Six digits: rounded here to four and again to a whole percent, a share can round up.
        "detection": r(t.loc["imagery_detection_rate", "mean"], 6),
        "false_per_minute": r(t.loc["false_per_minute", "mean"], 2),
        "latency_s": r(t.loc["latency_s", "mean"], 2),
        "n": int(t.loc["imagery_detection_rate", "n"]),
    }


def switch_continuous(summary: Path) -> dict:
    """EX5's S14: question 3's headline switch (sixth finger or rest, `ts_lr` on the 14 central
    channels) played continuously like answer 4: the sixth-finger and hand periods it turned on
    in, false switch-ons a minute of rest, and seconds after the cue (mean of patients' medians)."""
    t = pd.read_csv(summary / "ex5_live_switch_table.csv")
    t = t[(t.arm == "S14") & (t.population == "all")].set_index("metric")
    return {
        "finger_on": r(t.loc["sf_on_rate", "mean"], 6),
        "hand_on": r(t.loc["ah_on_rate", "mean"], 6),
        "false_per_minute": r(t.loc["false_per_minute", "mean"], 2),
        "latency_s": r(t.loc["latency_s", "mean"], 2),
        "n": int(t.loc["sf_on_rate", "n"]),
    }


def visual_check(summary: Path) -> dict:
    """The visual-cue check: `ts_lr` learned on runs 1 and 2 and tested on 3 and 4, reading the 14
    central channels or the 5 parieto-occipital ones, for both two-way tasks. The page says the
    central ones win on sixth finger or rest and lose on hand or sixth finger, so another outcome
    stops the build."""
    t = pd.read_csv(summary / "rq4_visual_cue_table.csv").set_index(["task", "channels"])
    out = {
        name: {
            "movement": r(t.loc[(task, "central_14"), "mean"], 6),
            "vision": r(t.loc[(task, "parieto_occipital_5"), "mean"], 6),
        }
        for name, task in (("rest", "T3_sf_vs_rest"), ("which", "T1_ah_vs_sf"))
    }
    rest, which = out["rest"], out["which"]
    if not (rest["movement"] > rest["vision"] and which["vision"] > which["movement"]):
        raise ValueError("the visual-cue check changed sides: the page's copy must be rewritten")
    return out


def own_hand(summary: Path) -> dict:
    """H3c's control, pre-registered: a decoder that learned only rest and the hand (`ah_proxy`)
    telling sixth finger from rest, and the test's category, for which the copy is written."""
    curves = pd.read_csv(summary / "calib_curves.csv")
    row = curves[
        (curves.scenario == "S2_new_command")
        & (curves.task == "T3_sf_vs_rest")
        & (curves.session == "pre")
        & (curves.method == "ah_proxy")
        & (curves.population == "all")
        & (curves.k == 0)
    ].iloc[0]
    tests = pd.read_csv(summary / "calib_confirmatory.csv")
    h3c = tests[
        tests.hypothesis.str.startswith("H3c")
        & (tests.role == "confirmatory")
        & (tests.session == "pre")
        & (tests.population == "all")
        & (tests.draw_basis == "random")
    ]
    if set(h3c.category) != {"inconclusive"}:
        raise ValueError(f"H3c is now {set(h3c.category)}: the page's copy must be rewritten")
    return {"mean": r(row["mean"], 6), "n": int(row.n), "h3c": "inconclusive"}


def prereg_replay(summary: Path) -> dict:
    """H4's pseudo-online replay, defined before any replay: the share of sixth-finger periods in
    which the three-class decoders gave the sixth-finger command, and their false activations a
    minute of rest, lowest and highest over the four decoders. The page says the expectation
    (most periods) was not met, so a replay that meets it stops the build."""
    t = pd.read_csv(summary / "rq4_pseudo_online_table.csv")
    t = t[t.population == "all"]
    finger = t[t.metric == "sf_detection_rate"]["mean"]
    false = t[t.metric == "false_per_minute"]["mean"]
    if finger.max() >= 0.5:
        raise ValueError("H4's replay now meets its expectation: rewrite the page's copy")
    return {
        "finger_detect": [r(finger.min(), 6), r(finger.max(), 6)],
        "false_per_minute": [r(false.min(), 2), r(false.max(), 2)],
        "methods": len(finger),
    }


def recipe_leak(summary: Path) -> dict:
    """The authors' own recipe rebuilt (`csp_lda_replica`), hand or sixth finger on the first
    session, scored the published way and leakage-free, and how many patients scored lower
    leakage-free."""
    table = pd.read_csv(summary / "rq1_table.csv")
    table = table[
        (table.task == "T1_ah_vs_sf")
        & (table.method == "csp_lda_replica")
        & (table.session == "pre")
        & (table.population == "all")
    ].set_index("protocol")
    values = pd.read_csv(summary / "rq1_subject_values.csv")
    values = values[
        (values.task == "T1_ah_vs_sf")
        & (values.method == "csp_lda_replica")
        & (values.session == "pre")
    ]
    wide = values.pivot_table(index="subject", columns="protocol", values="bal_acc")
    return {
        "paper_way": r(table.loc["paper_replica", "mean"], 6),
        "leakfree": r(table.loc["cv_leakfree", "mean"], 6),
        "n_positive": int((wide.paper_replica > wide.cv_leakfree).sum()),
        "n": int(table.loc["cv_leakfree", "n"]),
    }


def whole_pool(summary: Path) -> dict:
    """Rest, hand or sixth finger for a new patient after every practice trial: from nothing minus
    the transfer the study tried, in points (described, not tested), with the patients on each
    side; that transfer's target weight, for which the copy is written; and the whole pool's
    minutes at the recorded trial length."""
    pair = pd.read_csv(summary / "calib_pair_whole_pool.csv")
    row = pair[
        (pair.scenario == "S1_new_user") & (pair.task == "T2_rest_ah_sf") & (pair.session == "pre")
    ].iloc[0]
    if row.pair != "rct_tslr - ts_lr":
        raise ValueError(f"calib_pair_whole_pool.csv now pairs {row.pair}")
    hparams = pd.read_csv(summary / "transfer_hparams.csv")
    chosen = hparams[(hparams.method == "rct_tslr") & hparams.chosen]
    weight = float(chosen.target_weight.iloc[0])
    if weight != 1:
        raise ValueError(f"the transfer's target weight is now {weight}: rewrite the page's copy")
    minutes = pd.read_csv(summary / "calib_minutes.csv")
    m = minutes[
        (minutes.session == "pre") & (minutes.scenario == "S1_new_user") & (minutes.k == row.k)
    ].iloc[0]
    return {
        "diff_points": r(-row.mean_diff_points),
        "ci": [r(-row.ci_hi_points), r(-row.ci_lo_points)],
        "n_scratch_higher": int(row.n_second_higher),
        "n_transfer_higher": int(row.n_first_higher),
        "target_weight": int(weight),
        "minutes_recorded": r(m.minutes_recorded, 3),
    }


def healthy_benchmark(summary: Path) -> dict:
    """EX3's benchmark: healthy people's grasps of one hand, learned on day 1 and tested on day
    2, with `ts_lr` and `csp_lda` on all day-1 trials; the lowest and highest mean over the
    pairs of grasps, and over the two methods for all three."""
    bench = pd.read_csv(summary / "ex3_grasp_pretraining_benchmark_summary.csv")
    bench = bench[bench.train_set == "all"]
    pairs = bench[bench.task != "all_three"]["mean"]
    three = bench[bench.task == "all_three"]["mean"]
    if (bench.n != bench.n.iloc[0]).any():
        raise ValueError("the benchmark rows cover different numbers of people")
    return {
        "people": int(bench.n.iloc[0]),
        "pairs": [r(pairs.min()), r(pairs.max())],
        "three": [r(three.min()), r(three.max())],
    }


def benchmark(summary: Path) -> dict:
    """The page's benchmark: every headline score in one place. The table is balanced accuracy
    on the first session, each patient's model learning from runs 1 and 2 and tested on runs 3
    and 4; values keep six digits so the page's one-decimal rounding matches the paper's. The
    lines under it are setting up, another day, as if live, the leak and the demo model's size."""
    rq1 = pd.read_csv(summary / "rq1_table.csv")
    rq1 = rq1[(rq1.session == "pre") & (rq1.population == "all")].set_index(
        ["task", "method", "protocol"]
    )
    dl = pd.read_csv(summary / "dl_baselines_table.csv").drop_duplicates()
    dl = dl[(dl.protocol == "chrono") & (dl.method == "eegnet_scratch")].set_index("task")
    ex4 = pd.read_csv(summary / "ex4_sf_command_table.csv").set_index(["section", "row"])
    ex1 = pd.read_csv(summary / "ex1_transfer_ah_sf_paired.csv").set_index("comparison")

    switch = ex4.loc[("part1", "ts_lr_c14")]
    if str(switch.headline) != "True":
        raise ValueError("ts_lr_c14 is no longer EX4's headline arm")
    sure = ex4.loc[("arm_R", "R (ts_lr_c14), accuracy when acting")]
    transfer = ex1.loc["B"]
    if transfer.arm != "eegnet_ea_ft k=all":
        raise ValueError(f"EX1's arm B is now {transfer.arm}")
    if abs(transfer.arm_mean - ex4.loc[("part2_T1", "T1_ea_ft, all windows"), "mean"]) > 1e-6:
        raise ValueError("EX1 and EX4 disagree on hand or sixth finger after learning from others")
    # Each task's best: the switch EX4 chose on runs 1 and 2 (its headline arm), the network
    # that first learned from the other patients, and for all three the demo's own model.
    best = {
        "T3_sf_vs_rest": {
            "method": "ts_lr_c14",
            "mean": r(switch["mean"], 6),
            "sure": r(sure["mean"], 6),
            "sure_share": r(sure.share_mean, 6),
            # The arm that scored higher on runs 3 and 4 but lower on runs 1 and 2.
            "not_chosen": r(ex4.loc[("part1", "T_ea_ft"), "mean"], 6),
        },
        "T1_ah_vs_sf": {"method": "eegnet_ea_ft", "mean": r(transfer.arm_mean, 6)},
        "T2_rest_ah_sf": {
            "method": "eegnet_scratch",
            "mean": r(dl.loc["T2_rest_ah_sf", "mean"], 6),
        },
    }
    chance = {key: c for key, _label, c in TASKS}
    rows = []
    for key, top in best.items():
        cells = {
            "csp_lda": rq1.loc[(key, "csp_lda", "chrono")],
            "ts_lr": rq1.loc[(key, "ts_lr", "chrono")],
            "eegnet_scratch": dl.loc[key],
        }
        if any(int(c.n) != 22 for c in cells.values()):
            raise ValueError(f"{key}: a benchmark cell does not cover all 22 patients")
        means = {m: r(c["mean"], 6) for m, c in cells.items()}
        if top["mean"] < max(means.values()):
            raise ValueError(f"{key}: the best column is below another method")
        rows.append({"key": key, "chance": r(chance[key]), **means, "best": top})

    curves = pd.read_csv(summary / "calib_curves.csv")
    curves = curves[
        (curves.scenario == "S1_new_user")
        & (curves.task == "T2_rest_ah_sf")
        & (curves.session == "pre")
        & (curves.population == "all")
        & (curves.k > 0)
    ].set_index(["method", "k"])

    def point(method: str, k: int) -> dict:
        row = curves.loc[(method, k)]
        return {"mean": r(row["mean"], 6), "minutes": r(row.minutes, 3)}

    lon = pd.read_csv(summary / "rq4_longitudinal_table.csv")
    lon = lon[(lon.session == "post") & (lon.population == "all")].set_index(["arm", "k"])
    live = pd.read_csv(summary / "rq4_pseudo_online_switch_table.csv")
    live = live[live.method == "eegnet_scratch"].set_index("metric")
    ex5 = pd.read_csv(summary / "ex5_live_switch_table.csv")
    ex5 = ex5[(ex5.arm == "S14") & (ex5.population == "all")].set_index("metric")
    demo = json.loads((summary / "demo_model.json").read_text())
    last = int(curves.loc["ts_lr"].index.max())
    return {
        "n": 22,
        "tasks": rows,
        "setup": {
            "from_others": point("rct_tslr", 1),
            "from_nothing": point("ts_lr", 1),
            "from_nothing_end": point("ts_lr", last),
            "from_others_end": point("rct_tslr", last),
        },
        "later": {
            "as_is": r(lon.loc[("pre_unchanged", 0), "mean"], 6),
            "re_setup": r(lon.loc[("recentred", 5), "mean"], 6),
            "k": 5,
        },
        # Played as if live: the demo's model read as one switch for any movement (post hoc),
        # the headline switch's sixth-finger periods, and the pre-registered replay's range.
        "live": {
            "demo": {
                "detection": r(live.loc["imagery_detection_rate", "mean"], 6),
                "false_per_minute": r(live.loc["false_per_minute", "mean"], 3),
            },
            "switch": {
                "finger_on": r(ex5.loc["sf_on_rate", "mean"], 6),
                "false_per_minute": r(ex5.loc["false_per_minute", "mean"], 3),
            },
            "prereg": prereg_replay(summary)["finger_detect"],
        },
        "leak": {
            "paper_way": r(rq1.loc[("T1_ah_vs_sf", "csp_lda", "paper_replica"), "mean"], 6),
            "leakfree": r(rq1.loc[("T1_ah_vs_sf", "csp_lda", "cv_leakfree"), "mean"], 6),
            "recipe_paper_way": r(
                rq1.loc[("T1_ah_vs_sf", "csp_lda_replica", "paper_replica"), "mean"], 6
            ),
            "recipe_leakfree": r(
                rq1.loc[("T1_ah_vs_sf", "csp_lda_replica", "cv_leakfree"), "mean"], 6
            ),
        },
        "model": {"parameters": model_parameters(), "bytes": demo["parity"]["bytes"]},
    }


def build() -> dict:
    """The page's numbers, from the results summaries."""
    summary = get_paths().root / "results" / "summary"

    dl = pd.read_csv(summary / "dl_baselines_subject_values.csv")
    dl_table = pd.read_csv(summary / "dl_baselines_table.csv")
    tasks = []
    for key, label, chance in TASKS:
        mine = (dl.task == key) & (dl.method == "eegnet_scratch") & (dl.protocol == "chrono")
        rows = dl[mine & (dl.session == "pre")]
        t = dl_table
        row = t[(t.task == key) & (t.method == "eegnet_scratch") & (t.protocol == "chrono")].iloc[0]
        tasks.append(
            {
                "key": key,
                "label": label,
                "chance": r(chance),
                "mean": r(row["mean"]),
                "ci": [r(row.ci_lo), r(row.ci_hi)],
                "values": [r(v) for v in rows.sort_values("subject").bal_acc],
            }
        )

    rq1 = pd.read_csv(summary / "rq1_subject_values.csv")
    sel = rq1[
        (rq1.task == "T1_ah_vs_sf")
        & (rq1.method == "csp_lda")
        & (rq1.feature == "bandpower")
        & (rq1.session == "pre")
    ]
    wide = sel.pivot_table(index="subject", columns="protocol", values="bal_acc")
    stats = pd.read_csv(summary / "rq1_stats.csv")
    h1 = stats[stats.test_id == "H1"].iloc[0]
    leak = {
        "subjects": list(wide.index),
        "replica": [r(v) for v in wide.paper_replica],
        "leakfree": [r(v) for v in wide.cv_leakfree],
        "mean_replica": r(wide.paper_replica.mean()),
        "mean_leakfree": r(wide.cv_leakfree.mean()),
        "mean_diff_points": r(h1.mean_diff, 1),
        "n_positive": int((wide.paper_replica > wide.cv_leakfree).sum()),
        # The paper's CSP+LDA means on the pre session: BCI group, then traditional group.
        "published": [0.8509, 0.8602],
    }

    curves = pd.read_csv(summary / "calib_curves.csv")

    def curve(method: str) -> list[dict]:
        c = curves[
            (curves.scenario == "S1_new_user")
            & (curves.task == "T2_rest_ah_sf")
            & (curves.session == "pre")
            & (curves.method == method)
            & (curves.population == "all")
            & (curves.k > 0)
        ].sort_values("k")
        return [
            {
                "k": int(x.k),
                "minutes": r(x.k * 2 * SECONDS_PER_TRIAL / 60, 3),
                "mean": r(x.mean),
                "ci": [r(x.ci_lo), r(x.ci_hi)],
            }
            for x in c.itertuples()
        ]

    erd = pd.read_csv(summary / "eda_erd_values.csv")
    # Mirrored, so C3 is over the hemisphere that moves the affected hand.
    c3 = erd[(erd.session == "pre") & (erd.band == "mu") & (erd.channel == "C3")]
    erd_out = {
        cls: {
            "values": [r(v, 1) for v in c3[c3["class"] == cls].sort_values("subject").erd_percent],
            "mean": r(c3[c3["class"] == cls].erd_percent.mean(), 1),
        }
        for cls in ("affected_hand", "sixth_finger")
    }

    switch = pd.read_csv(summary / "rq4_pseudo_online_switch_table.csv")
    sw = switch[switch.method == "eegnet_scratch"].set_index("metric")
    demo = json.loads((summary / "demo_model.json").read_text())

    # Weeks later: the first session's model on the later sessions, as it is and after a
    # short re-setup (5 new trials per command, re-centred); same method as `ts_lr`.
    lon = pd.read_csv(summary / "rq4_longitudinal_table.csv")
    lon = lon[lon.population == "all"]

    def lon_row(session: str, arm: str, k: int) -> dict:
        row = lon[(lon.session == session) & (lon.arm == arm) & (lon.k == k)].iloc[0]
        return {"mean": r(row["mean"]), "ci": [r(row.ci_lo), r(row.ci_hi)], "n": int(row.n)}

    within = curves[
        (curves.scenario == "S1_new_user")
        & (curves.task == "T2_rest_ah_sf")
        & (curves.session == "pre")
        & (curves.method == "ts_lr")
        & (curves.population == "all")
    ].sort_values("k")

    # The same leak elsewhere: two public motor-imagery datasets (RQ1b) and depression
    # detection from resting EEG (RQ5), each scored the leaky way and fairly.
    rq1b = pd.read_csv(summary / "rq1b_table.csv").set_index(["dataset", "protocol"])
    rq1b_h = pd.read_csv(summary / "rq1b_stats.csv")
    rq1b_h = rq1b_h[rq1b_h.test_id == "H1b"].set_index("dataset")
    rq5 = pd.read_csv(summary / "rq5_table.csv").set_index(["dataset", "pipeline", "protocol"])
    rq5_h = pd.read_csv(summary / "rq5_stats.csv").set_index(["dataset", "pipeline"])
    # Mumtaz with the diagnoses shuffled among people: each protocol's mean over the shuffles.
    rq5_null = pd.read_csv(summary / "rq5_null.csv").groupby("protocol").ba.agg(["mean", "count"])
    elsewhere = {
        "motor": [
            {
                "dataset": ds,
                "leaky": r(rq1b.loc[(ds, "paper_replica"), "mean"]),
                "fair": r(rq1b.loc[(ds, "cv_leakfree"), "mean"]),
                "points": r(rq1b_h.loc[ds, "mean_diff"], 1),
                "n": int(rq1b.loc[(ds, "cv_leakfree"), "n"]),
            }
            for ds in ("BNCI2014_001", "Cho2017")
        ],
        "depression": [
            {
                "dataset": ds,
                "pipeline": pl,
                "leaky": r(rq5.loc[(ds, pl, "segment_cv"), "ba"]),
                "fair": r(rq5.loc[(ds, pl, "subject_cv"), "ba"]),
                "points": r(rq5_h.loc[(ds, pl), "inflation_points"], 1),
                "n": int(rq5.loc[(ds, pl, "subject_cv"), "n_subjects"]),
            }
            for ds in ("mumtaz", "modma")
            for pl in ("bp_lr", "ts_lr")
        ],
        "depression_shuffled": {
            "leaky": r(rq5_null.loc["segment_cv", "mean"]),
            "fair": r(rq5_null.loc["subject_cv", "mean"]),
            "shuffles": int(rq5_null.loc["segment_cv", "count"]),
        },
    }

    # How long fitting takes: one CSP+LDA per patient on the Mac, and the leave-one-out
    # EEGNets that learn from all other patients, on a cloud GPU.
    runtime = pd.read_csv(summary / "rq1_runtime.csv")
    csp_fit = runtime[(runtime.method == "csp_lda") & (runtime.protocol == "chrono")].iloc[0]
    pretrain = pd.read_csv(summary / "dl_pretrain_table.csv")

    data = {
        "sources": [
            "results/summary/dl_baselines_subject_values.csv",
            "results/summary/dl_baselines_table.csv",
            "results/summary/rq1_subject_values.csv",
            "results/summary/rq1_stats.csv",
            "results/summary/calib_curves.csv",
            "results/summary/rq4_pseudo_online_switch_table.csv",
            "results/summary/demo_model.json",
            "results/summary/eda_erd_values.csv",
            "results/summary/rq4_longitudinal_table.csv",
            "results/summary/rq1b_table.csv",
            "results/summary/rq1b_stats.csv",
            "results/summary/rq5_table.csv",
            "results/summary/rq5_stats.csv",
            "results/summary/rq5_null.csv",
            "results/summary/rq1_runtime.csv",
            "results/summary/dl_pretrain_table.csv",
            "results/summary/ex4_sf_command_table.csv",
            "results/summary/ex4_sf_command_per_patient.csv",
            "results/summary/ex4_sf_command_coverage.csv",
            "results/summary/ex3_grasp_pretraining_benchmark_summary.csv",
            "results/summary/ex5_live_switch_table.csv",
            "results/summary/ex5_live_switch_checks.json",
            "results/summary/rq1_table.csv",
            "results/summary/ex1_transfer_ah_sf_paired.csv",
            "results/summary/calib_pair_whole_pool.csv",
            "results/summary/calib_minutes.csv",
            "results/summary/calib_confirmatory.csv",
            "results/summary/transfer_hparams.csv",
            "results/summary/rq4_visual_cue_table.csv",
            "results/summary/rq4_pseudo_online_table.csv",
            "web/public/demo/model.onnx",
            "web/public/demo/predictions.json",
            "mne colin27_1005 template",
        ],
        "electrodes": electrodes(),
        "erd": erd_out,
        "tasks": tasks,
        "leak": {**leak, "recipe": recipe_leak(summary)},
        "calibration": {"scratch": curve("ts_lr"), "transfer": curve("rct_tslr")},
        "whole_pool": whole_pool(summary),
        "switch": {
            "detection": r(sw.loc["imagery_detection_rate", "mean"]),
            "detection_ci": [
                r(sw.loc["imagery_detection_rate", "ci_lo"]),
                r(sw.loc["imagery_detection_rate", "ci_hi"]),
            ],
            "false_per_minute": r(sw.loc["false_per_minute", "mean"], 2),
            "latency_s": r(sw.loc["latency_s", "mean"], 2),
            "n": int(sw.loc["imagery_detection_rate", "n"]),
            "central": central_switch(summary),
            "prereg": prereg_replay(summary),
        },
        "later": {
            "same_session": r(within.iloc[-1]["mean"]),
            "post": {
                "as_is": lon_row("post", "pre_unchanged", 0),
                "re_setup": lon_row("post", "recentred", 5),
            },
            "follow": {
                "as_is": lon_row("follow", "pre_unchanged", 0),
                "re_setup": lon_row("follow", "recentred", 5),
            },
        },
        "elsewhere": elsewhere,
        "runtime": {
            "csp_lda_fit_s": r(csp_fit.mean_fit_seconds, 2),
            "pretrain_s_median": r(pretrain.seconds.median(), 0),
            "pretrain_n": len(pretrain),
            "pretrain_on_gpu": bool((pretrain.device == "cuda").all()),
        },
        "demo": {
            "subject": demo["subject"],
            "held_out_bal_acc": r(demo["held_out_bal_acc"]),
            # The score the demo patient was chosen by (protocol §10), and the group's median.
            "chosen_by_bal_acc": r(
                next(c for c in demo["choice"]["candidates"] if c["subject"] == demo["subject"])[
                    "chrono_bal_acc"
                ]
            ),
            "group_median_bal_acc": r(demo["choice"]["cohort_median_chrono"]),
            "trials": demo["trials_whole"],
            "trials_total": demo["trials_total"],
            "training_trials": demo["n_training_trials"],
            "model_bytes": demo["parity"]["bytes"],
            "parameters": model_parameters(),
            **demo_readings(),
        },
        "sixth": {
            **sixth_command(summary),
            "continuous": switch_continuous(summary),
            "visual": visual_check(summary),
            "own_hand": own_hand(summary),
            "healthy": healthy_benchmark(summary),
        },
        "benchmark": benchmark(summary),
    }
    return data


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--facts-only", action="store_true", help="write demo_page.json alone")
    args = ap.parse_args()
    root = get_paths().root
    root.joinpath(*OUT_FACTS).write_text(json.dumps(demo_facts(), indent=1) + "\n")
    if args.facts_only:
        print(f"wrote {'/'.join(OUT_FACTS)}")
        return
    out = root.joinpath(*OUT)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build(), indent=1) + "\n")
    root.joinpath(*OUT_HEAD).write_text(json.dumps(head_model(), separators=(",", ":")) + "\n")
    print(f"wrote {'/'.join(OUT)} and {'/'.join(OUT_HEAD)}")


if __name__ == "__main__":
    main()
