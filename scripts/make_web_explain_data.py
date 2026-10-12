"""The numbers behind the demo page's explanatory figures (web/src/explain/data.json).

uv run python scripts/make_web_explain_data.py

Every value is read from a results file named in the output's "sources", so the page
never carries a number typed by hand. Run again whenever those summaries change.
"""

from __future__ import annotations

import json

import mne
import numpy as np
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
        # The authors' reported pre-session means (LDA and SVM, both groups), 05-DATASET-DOSSIER.md.
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
        },
        "demo": {
            "subject": demo["subject"],
            "held_out_bal_acc": r(demo["held_out_bal_acc"]),
            "trials": demo["trials_whole"],
            "training_trials": demo["n_training_trials"],
            "model_bytes": demo["parity"]["bytes"],
        },
    }
    return data


def main() -> None:
    out = get_paths().root.joinpath(*OUT)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build(), indent=1) + "\n")
    print(f"wrote {'/'.join(OUT)}")


if __name__ == "__main__":
    main()
