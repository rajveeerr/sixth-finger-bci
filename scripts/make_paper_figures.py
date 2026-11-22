"""Draw the paper's result figures from the stored summaries, in one style (P13).

uv run --with brotli==1.2.1 python scripts/make_paper_figures.py

Draws nothing a results file does not state: every mean and 95 % bootstrap CI is a row of a
summary table, every dot a stored per-patient value, and each group of dots must average to its
table's mean or nothing is drawn. brotli is needed once, to cut Inter (the typeface of the page's
drawings) from the web font into the temp folder.

- paper_leak: CSP+LDA, hand vs sixth finger, pre, per patient under the four protocols
  (rq1_subject_values.csv, rq1_table.csv);
- paper_calibration: a new user, three classes, pre, re-centred transfer and from scratch
  against the minutes of labelled recording (calib_curves.csv, calib_subject_values.csv);
- paper_later: the first session's TS+LR decoder two weeks and a month later, unchanged and
  adapted (rq4_longitudinal_table.csv, rq4_longitudinal.csv, rq4_longitudinal_reference.csv);
- paper_switch: the central sixth-finger switch and hand vs finger per patient, and how often
  the switch turns on (ex4_sf_command_table.csv, ex4_sf_command_per_patient.csv,
  ex5_live_switch_table.csv, ex5_live_switch_values.csv);
- paper_networks: EEGNet trained on each patient against CSP+LDA and TS+LR (leave one run out),
  and the pre-trained EEGNet with no labelled trial, for the three tasks (dl_baselines_table.csv,
  dl_baselines_subject_values.csv, rq1_subject_values.csv, dl_zeroshot_table.csv,
  dl_zeroshot_subject_values.csv).

uv run --with brotli==1.2.1 python scripts/make_paper_figures.py paper_networks   # only some

Writes docs/figures/paper_<name>.{pdf,png}, each at most one IEEE column wide (3.5 in) with no
text under 7 pt, and copies the PDFs to paper/figures/.
"""

from __future__ import annotations

import shutil
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from sixthfinger.paths import get_paths
from sixthfinger.viz.plots import (
    CHANCE_GREY,
    MEAN_INK,
    PAPER_PT,
    PATIENT_GREY,
    SECOND_INK,
    check_print,
    check_width,
    save,
    use_paper_style,
)

# The per-patient files store four to six decimals, so their mean can sit this far from the table's.
TOLERANCE = 5e-5
PRE, T1, T2 = "pre", "T1_ah_vs_sf", "T2_rest_ah_sf"
S1 = "S1_new_user"


def agree(name: str, values: pd.Series, mean: float, n: int) -> None:
    if len(values) != n or abs(values.mean() - mean) > TOLERANCE:
        raise SystemExit(f"{name}: per-patient values do not give the table's mean")


def chance(ax, y: float, horizontal: bool = True, side: str = "right", below: bool = False):
    style = dict(color=CHANCE_GREY, lw=0.7, ls=(0, (3, 2)), zorder=1)
    if horizontal:
        ax.axhline(y, **style)
        at, dx = (1, -1) if side == "right" else (0, 2)
        dy, va = (-2, "top") if below else (2, "bottom")
        ax.annotate("chance", (at, y), xycoords=("axes fraction", "data"), xytext=(dx, dy),
                    textcoords="offset points", ha=side, va=va, color=CHANCE_GREY)  # fmt: skip
    else:
        ax.axvline(y, **style)
        at, dx = (0, 2) if side == "right" else (1, -2)
        ax.annotate("chance", (y, at), xycoords=("data", "axes fraction"), xytext=(dx, 1 - 2 * at),
                    textcoords="offset points", ha="left" if side == "right" else "right",
                    va="bottom" if at == 0 else "top", color=CHANCE_GREY)  # fmt: skip


def dots(ax, at: float, values: pd.Series, rng, vertical: bool = True, spread: float = 0.12):
    jitter = at + rng.uniform(-spread, spread, len(values))
    x, y = (jitter, 100 * values) if vertical else (100 * values, jitter)
    ax.scatter(x, y, s=5, color=PATIENT_GREY, lw=0, zorder=2)


def mean_ci(ax, at: float, row, vertical: bool = True, color: str = MEAN_INK) -> None:
    mean, lo, hi = 100 * row["mean"], 100 * row.ci_lo, 100 * row.ci_hi
    err = [[mean - lo], [hi - mean]]
    if vertical:
        ax.errorbar(at, mean, yerr=err, fmt="o", ms=3.2, color=color, elinewidth=1.1, capsize=0,
                    zorder=4)  # fmt: skip
    else:
        ax.errorbar(mean, at, xerr=err, fmt="o", ms=3.2, color=color, elinewidth=1.1, capsize=0,
                    zorder=4)  # fmt: skip


def grid(ax, axis: str = "y") -> None:
    ax.grid(axis=axis, color="#ececec", lw=0.5)
    ax.set_axisbelow(True)


def leak(summary) -> plt.Figure:
    protocols = ["paper_replica", "cv_leakfree", "loro", "chrono"]
    labels = [
        "CSP fitted\non all trials",
        "leakage-free\nCV",
        "leave one\nrun out",
        "chrono-\nlogical",
    ]
    table = pd.read_csv(summary / "rq1_table.csv")
    table = table[(table.task == T1) & (table.method == "csp_lda")
                  & (table.feature == "bandpower") & (table.session == PRE)
                  & (table.population == "all")].set_index("protocol")  # fmt: skip
    values = pd.read_csv(summary / "rq1_subject_values.csv")
    values = values[(values.experiment == "rq1_benchmark") & (values.task == T1)
                    & (values.method == "csp_lda") & (values.session == PRE)]  # fmt: skip
    if values.duplicated(["subject", "protocol"]).any():
        raise SystemExit("leak: a patient has two values under one protocol")
    wide = values.pivot_table(index="subject", columns="protocol", values="bal_acc")[protocols]
    for p in protocols:
        agree(f"leak {p}", wide[p], table.loc[p, "mean"], int(table.loc[p, "n"]))

    fig, ax = plt.subplots(figsize=(3.3, 2.15))
    x = np.arange(len(protocols))
    for _, row in wide.iterrows():
        ax.plot(x, 100 * row.to_numpy(), color=PATIENT_GREY, lw=0.6, zorder=2)
    rows = table.loc[protocols]
    ax.plot(x, 100 * rows["mean"].to_numpy(), color=MEAN_INK, lw=1.3, zorder=3)
    for i, p in enumerate(protocols):
        mean_ci(ax, i, rows.loc[p])
        ax.annotate(f"{100 * rows.loc[p, 'mean']:.1f}", (i, 100 * rows.loc[p, "ci_hi"]),
                    xytext=(0, 2), textcoords="offset points", ha="center", va="bottom",
                    fontweight="semibold")  # fmt: skip
    chance(ax, 50, side="left")
    ax.set_xticks(x, labels)
    ax.set_xlim(-0.35, len(protocols) - 0.65)
    ax.set_ylim(35, 100)
    ax.set_ylabel("Balanced accuracy (%)")
    grid(ax)
    fig.tight_layout(pad=0.2)
    return fig


def calibration(summary) -> plt.Figure:
    curves = pd.read_csv(summary / "calib_curves.csv")
    curves = curves[(curves.scenario == S1) & (curves.task == T2) & (curves.session == PRE)
                    & (curves.population == "all") & curves["mean"].notna()]  # fmt: skip
    values = pd.read_csv(summary / "calib_subject_values.csv")
    values = values[(values.scenario == S1) & (values.task == T2) & (values.session == PRE)]

    fig, ax = plt.subplots(figsize=(3.3, 2.1))
    styles = {"rct_tslr": (MEAN_INK, "-", MEAN_INK), "ts_lr": (SECOND_INK, (0, (4, 2)), "white")}
    for method, (color, ls, face) in styles.items():
        rows = curves[curves.method == method].sort_values("k")
        for _, row in rows.iterrows():
            mine = values[(values.method == method) & (values.k == row.k)].bal_acc.dropna()
            agree(f"calibration {method} k={row.k}", mine, row["mean"], int(row.n))
        # k = 0 uses only unlabelled rest, so it sits at no labelled minutes.
        minutes = np.where(rows.k == 0, 0.0, rows.minutes)
        ax.fill_between(minutes, 100 * rows.ci_lo, 100 * rows.ci_hi, color=color, alpha=0.13,
                        lw=0, zorder=1)  # fmt: skip
        ax.plot(minutes, 100 * rows["mean"], color=color, ls=ls, lw=1.2, marker="o", ms=3,
                mfc=face, mec=color, mew=0.9, zorder=3)  # fmt: skip
    chance(ax, 100 / 3)
    ax.annotate("re-centred transfer (RCT-TS+LR)", (9.6, 63.4), ha="right", va="bottom",
                color=MEAN_INK)  # fmt: skip
    ax.annotate("from scratch (TS+LR)", (3.0, 46.0), ha="left", va="center", color=SECOND_INK)
    ax.annotate("k = 0, rest only", (0, 52.6), xytext=(0.25, 66.5), ha="left", va="center",
                color=SECOND_INK, arrowprops=dict(arrowstyle="-", color=SECOND_INK, lw=0.6,
                                                  shrinkA=1, shrinkB=2))  # fmt: skip
    ax.set_xlim(-0.3, 9.8)
    ax.set_ylim(25, 70)
    ax.set_xticks([0, 2, 4, 6, 8])
    ax.set_xlabel("Labelled recording (min, nominal 14 s per trial)")
    ax.set_ylabel("Balanced accuracy,\nthree classes (%)")
    grid(ax)
    fig.tight_layout(pad=0.2)
    return fig


def later(summary) -> plt.Figure:
    arms = [
        ("pre_unchanged", 0, "unchanged"),
        ("recentred", 0, "re-centred, no new trials"),
        ("new_only", 5, "5 new trials alone"),
        ("pooled", 5, "old + 5 new, pooled"),
        ("recentred", 5, "old + 5 new, re-centred"),
    ]
    table = pd.read_csv(summary / "rq4_longitudinal_table.csv")
    table = table[table.population == "all"]
    values = pd.read_csv(summary / "rq4_longitudinal.csv")
    reference = pd.read_csv(summary / "rq4_longitudinal_reference.csv")
    reference = reference[reference.reference_session == PRE]
    rng = np.random.default_rng(0)  # vertical jitter of the dots only

    fig, axes = plt.subplots(1, 2, figsize=(3.3, 2.05), sharey=True)
    sessions = [("post", "Two weeks later"), ("follow", "A month later")]
    for ax, (session, title) in zip(axes, sessions, strict=True):
        for i, (arm, k, _) in enumerate(arms):
            row = table[(table.session == session) & (table.arm == arm) & (table.k == k)].iloc[0]
            mine = values[(values.session == session) & (values.arm == arm) & (values.k == k)]
            agree(f"later {session} {arm} k={k}", mine.bal_acc, row["mean"], int(row.n))
            dots(ax, i, mine.bal_acc, rng, vertical=False, spread=0.16)
            mean_ci(ax, i, row, vertical=False)
        within = reference[reference.session == session].reference_mean.unique()
        if len(within) != 1:
            raise SystemExit(f"later {session}: no single within-session reference")
        ax.axvline(100 * within[0], color=SECOND_INK, lw=0.8, zorder=1)
        ax.annotate("first\nsession", (100 * within[0], len(arms) - 0.45), xytext=(2, 0),
                    textcoords="offset points", ha="left", va="top", color=SECOND_INK,
                    linespacing=0.95)  # fmt: skip
        chance(ax, 100 / 3, horizontal=False)
        ax.set_title(f"{title}\nn = {int(row.n)}", linespacing=1.05)
        ax.set_xlim(25, 85)
        ax.set_xticks([40, 60, 80])
        grid(ax, "x")
    axes[0].set_yticks(range(len(arms)), [label for *_, label in arms])
    axes[0].set_ylim(len(arms) + 0.6, -0.6)
    axes[1].tick_params(axis="y", length=0)
    fig.supxlabel("Balanced accuracy, three classes (%)", x=0.66, y=0.0, fontsize=PAPER_PT)
    fig.tight_layout(pad=0.2, w_pad=0.6)
    return fig


def switch(summary) -> plt.Figure:
    ex4 = pd.read_csv(summary / "ex4_sf_command_table.csv").set_index("row")
    ex4_patients = pd.read_csv(summary / "ex4_sf_command_per_patient.csv")
    ex5 = pd.read_csv(summary / "ex5_live_switch_table.csv")
    ex5 = ex5[(ex5.arm == "S14") & (ex5.population == "all")].set_index("metric")
    ex5_patients = pd.read_csv(summary / "ex5_live_switch_values.csv")
    ex5_patients = ex5_patients[ex5_patients.arm == "S14"]
    rng = np.random.default_rng(0)  # jitter of the dots only

    # Placed by hand: a shared grid would indent the lower panel by the upper one's labels.
    fig = plt.figure(figsize=(3.3, 2.7))
    top = fig.add_axes((0.31, 0.78, 0.66, 0.2))
    bottom = fig.add_axes((0.12, 0.17, 0.85, 0.47))
    accuracy = [
        ("ts_lr_c14", "test_ts_lr_c14", "finger vs rest\n(TS+LR, central)"),
        ("T1_ea_ft, all windows", "test_T1_ea_ft", "hand vs finger\n(EEGNet)"),
    ]
    for i, (row_name, column, _) in enumerate(accuracy):
        row = ex4.loc[row_name]
        agree(f"switch {column}", ex4_patients[column], row["mean"], int(row.n))
        dots(top, i, ex4_patients[column], rng, vertical=False, spread=0.14)
        mean_ci(top, i, row, vertical=False)
    chance(top, 50, horizontal=False, side="left")
    top.set_yticks(range(len(accuracy)), [label for *_, label in accuracy])
    top.set_ylim(len(accuracy) - 0.45, -0.55)
    top.set_xlim(40, 101)
    top.set_xlabel("Balanced accuracy (%)")
    grid(top, "x")

    response = [
        (0, "trial_fire_rest", "rest"),
        (1, "trial_fire_ah", "hand"),
        (2, "trial_fire_sf", "finger"),
        (3.5, "ah_on_rate", "hand"),
        (4.5, "sf_on_rate", "finger"),
    ]
    for at, metric, _ in response:
        row = ex5.loc[metric]
        agree(f"switch {metric}", ex5_patients[metric], row["mean"], int(row.n))
        dots(bottom, at, ex5_patients[metric], rng)
        mean_ci(bottom, at, row)
    bottom.axvline(2.75, color="#dddddd", lw=0.6)
    bottom.set_xticks([at for at, *_ in response], [label for *_, label in response])
    bottom.set_xlim(-0.5, 5.0)
    bottom.set_ylim(-3, 103)
    bottom.set_ylabel("Switched on (%)")
    for at, text in ((1, "single test windows"), (4, "imagery periods,\nplayed continuously")):
        bottom.annotate(text, (at, 0), xycoords=("data", "axes fraction"), xytext=(0, -13.5),
                        textcoords="offset points", ha="center", va="top", color=SECOND_INK,
                        linespacing=0.95)  # fmt: skip
    grid(bottom)
    return fig


def networks(summary) -> plt.Figure:
    tasks = [
        (T1, "Hand or sixth finger", 50),
        (T2, "Rest, hand or finger", 100 / 3),
        ("T3_sf_vs_rest", "Sixth finger or rest", 50),
    ]
    methods = [
        ("eegnet_scratch", "EEGNet, own data"),
        ("csp_lda", "CSP+LDA"),
        ("ts_lr", "TS+LR"),
        ("zero_shot", "EEGNet, others only\n(no labelled trial)"),
    ]
    table = pd.read_csv(summary / "dl_baselines_table.csv")
    table = table[table.protocol == "loro"].set_index(["task", "method"])
    own = pd.read_csv(summary / "dl_baselines_subject_values.csv")
    own = own[(own.protocol == "loro") & (own.session == PRE)]
    classical = pd.read_csv(summary / "rq1_subject_values.csv")
    classical = classical[(classical.protocol == "loro") & (classical.session == PRE)
                          & (classical.feature == "bandpower")]  # fmt: skip
    zero = pd.read_csv(summary / "dl_zeroshot_table.csv").set_index("task")
    zero_values = pd.read_csv(summary / "dl_zeroshot_subject_values.csv")
    zero_values = zero_values[zero_values.session == PRE]
    rng = np.random.default_rng(0)  # vertical jitter of the dots only

    fig, axes = plt.subplots(3, 1, figsize=(3.3, 3.5), sharex=True)
    for ax, (task, title, level) in zip(axes, tasks, strict=True):
        for i, (method, _) in enumerate(methods):
            if method == "zero_shot":
                row = zero.loc[task]
                mine = zero_values[zero_values.task == task].bal_acc
            else:
                row = table.loc[(task, method)]
                source = own if method == "eegnet_scratch" else classical
                mine = source[(source.task == task) & (source.method == method)].bal_acc
            agree(f"networks {task} {method}", mine, row["mean"], int(row.n))
            dots(ax, i, mine, rng, vertical=False, spread=0.16)
            mean_ci(ax, i, row, vertical=False)
        ax.axvline(level, color=CHANCE_GREY, lw=0.7, ls=(0, (3, 2)), zorder=1)
        ax.set_title(title, loc="left", fontweight="semibold")
        ax.set_yticks(range(len(methods)), [label for _, label in methods])
        ax.set_ylim(len(methods) - 0.45, -0.55)
        grid(ax, "x")
    axes[-1].annotate("chance", (50, 0), xycoords=("data", "axes fraction"), xytext=(-2, 2),
                     textcoords="offset points", ha="right", va="bottom",
                     color=CHANCE_GREY)  # fmt: skip
    axes[-1].set_xlim(20, 101)
    axes[-1].set_xticks([20, 40, 60, 80, 100])
    axes[-1].set_xlabel("Balanced accuracy (%)")
    fig.tight_layout(pad=0.2, h_pad=0.6)
    return fig


FIGURES = {
    "paper_leak": leak,
    "paper_calibration": calibration,
    "paper_later": later,
    "paper_switch": switch,
    "paper_networks": networks,
}


def main() -> None:
    paths = get_paths()
    summary = paths.root / "results" / "summary"
    use_paper_style(paths.root)
    only = sys.argv[1:]
    unknown = sorted(set(only) - set(FIGURES))
    if unknown:
        raise SystemExit(f"unknown figure: {', '.join(unknown)}")
    for name, draw in FIGURES.items():
        if only and name not in only:
            continue
        fig = draw(summary)
        check_print(fig)
        save(fig, paths.figures, name)
        width = check_width(paths.figures / f"{name}.pdf")
        paper = paths.root / "paper" / "figures" / f"{name}.pdf"
        shutil.copyfile(paths.figures / f"{name}.pdf", paper)
        print(f"wrote {paths.figures / name}.pdf/.png ({width:.2f} in wide) and {paper}")


if __name__ == "__main__":
    main()
