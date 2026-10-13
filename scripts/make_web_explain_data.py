"""The numbers behind the demo page's explanatory figures (web/src/explain/data.json).

uv run python scripts/make_web_explain_data.py

Every value is read from a results file named in the output's "sources", so the page
never carries a number typed by hand. Run again whenever those summaries change.
"""

from __future__ import annotations

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
            "results/summary/rq1_runtime.csv",
            "results/summary/dl_pretrain_table.csv",
            "web/public/demo/model.onnx",
            "mne colin27_1005 template",
        ],
        "electrodes": electrodes(),
        "erd": erd_out,
        "tasks": tasks,
        "leak": leak,
        "calibration": {"scratch": curve("ts_lr"), "transfer": curve("rct_tslr")},
        "switch": {
            "detection": r(sw.loc["imagery_detection_rate", "mean"]),
            "detection_ci": [
                r(sw.loc["imagery_detection_rate", "ci_lo"]),
                r(sw.loc["imagery_detection_rate", "ci_hi"]),
            ],
            "false_per_minute": r(sw.loc["false_per_minute", "mean"], 2),
            "latency_s": r(sw.loc["latency_s", "mean"], 2),
            "n": int(sw.loc["imagery_detection_rate", "n"]),
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
        },
    }
    return data


def main() -> None:
    root = get_paths().root
    out = root.joinpath(*OUT)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build(), indent=1) + "\n")
    root.joinpath(*OUT_HEAD).write_text(json.dumps(head_model(), separators=(",", ":")) + "\n")
    print(f"wrote {'/'.join(OUT)} and {'/'.join(OUT_HEAD)}")


if __name__ == "__main__":
    main()
