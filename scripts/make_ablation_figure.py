"""Draw the ablation summary of the college paper from the stored paired comparisons.

uv run --with brotli==1.2.1 python scripts/make_ablation_figure.py

One row per component comparison that has a paired difference with a 95 % bootstrap CI in a
results file: the difference (variant minus reference, points of balanced accuracy) as a dot
with its interval, and the two accuracies beside it. Filled dots are pre-registered
comparisons, open dots were added after the confirmatory results. Every value is a cell of a
file under results/summary/; nothing is typed in. Writes docs/figures/paper_ablation.{pdf,png}
(the full text width of the college paper, 7.16 in) and copies the PDF to paper/figures/.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from sixthfinger.paths import get_paths
from sixthfinger.viz.plots import (
    CHANCE_GREY,
    MEAN_INK,
    SECOND_INK,
    check_print,
    save,
    use_paper_style,
)

TEXT_WIDTH_IN = 7.16
PRE, S1, T2 = "pre", "S1_new_user", "T2_rest_ah_sf"


@dataclass
class Row:
    label: str
    diff: float
    lo: float
    hi: float
    variant: float
    reference: float
    planned: bool


def one(df: pd.DataFrame, **where) -> pd.Series:
    """The single row of df matching every column=value given."""
    mask = pd.Series(True, index=df.index)
    for column, value in where.items():
        mask &= df[column] == value
    if mask.sum() != 1:
        raise SystemExit(f"expected one row for {where}, found {int(mask.sum())}")
    return df[mask].iloc[0]


def paired(df: pd.DataFrame, label: str, planned: bool = False, **where) -> Row:
    """A row of the follow-ups' paired files: points for the difference, fractions for the arms."""
    r = one(df, **where)
    return Row(label, r.diff_points, r.diff_ci_lo, r.diff_ci_hi, 100 * r.arm_mean,
               100 * r.base_mean, planned)  # fmt: skip


def transfer_rows(summary: Path) -> list[Row]:
    curves = pd.read_csv(summary / "calib_curves.csv")
    curves = curves[(curves.scenario == S1) & (curves.task == T2) & (curves.session == PRE)
                    & (curves.population == "all")]  # fmt: skip

    def mean(method: str, k: int) -> float:
        return 100 * one(curves, method=method, k=k)["mean"]

    per_k = pd.read_csv(summary / "calib_h2a_per_k.csv")
    rows = []
    for k in (1, 5, 10):
        r = one(per_k, k=k)
        rows.append(Row(f"re-centred transfer vs none, k = {k}", r.mean_diff, r.ci_lo, r.ci_hi,
                        mean("rct_tslr", k), mean("ts_lr", k), True))  # fmt: skip
    whole = pd.read_csv(summary / "calib_pair_whole_pool.csv")
    r = one(whole, scenario=S1, task=T2, session=PRE, pair="rct_tslr - ts_lr")
    rows.append(Row("the same, whole pool (descriptive, not tested)", r.mean_diff_points,
                    r.ci_lo_points, r.ci_hi_points, mean("rct_tslr", int(r.k)),
                    mean("ts_lr", int(r.k)), True))  # fmt: skip
    return rows


def mirror_rows(summary: Path) -> list[Row]:
    table = pd.read_csv(summary / "rq4_mirror_table.csv")
    rows = []
    for method, name in (("rct_tslr", "re-centred transfer"), ("pooled_tslr", "pooled TS+LR")):
        r = one(table, method=method, k=5)
        label = f"mirrored vs not, {name}, k = 5"
        rows.append(Row(label, 100 * r.mean_diff, 100 * r.ci_lo, 100 * r.ci_hi,
                        100 * r.mean_mirrored, 100 * r.mean_unmirrored, True))  # fmt: skip
    return rows


def slow_rows(summary: Path) -> list[Row]:
    table = pd.read_csv(summary / "ex2_slow_waves_paired.csv")
    posthoc = pd.read_csv(summary / "ex2_slow_waves_posthoc.csv")

    def row(df, label, **where):
        r = one(df, **where)
        return Row(label, 100 * r.mean_diff, 100 * r.ci_lo, 100 * r.ci_hi, 100 * r.arm_mean,
                   100 * r.baseline_mean, False)  # fmt: skip

    return [
        row(table, "raw 8–30 Hz, 59 channels vs published files", window="primary", arm="R59",
            baseline="B0"),
        row(table, "slow waves, 59 channels vs published files", window="primary", arm="S59",
            baseline="B0"),
        row(table, "the same, window from the cue", window="secondary", arm="S59", baseline="B0"),
        row(posthoc, "slow waves without the 7 nearest the eyes", window="primary",
            arm="S52_no_near_eyes", baseline="B0"),
        row(table, "slow waves vs TS+LR, both on 14 central", window="primary", arm="S_central",
            baseline="B0_central"),
    ]  # fmt: skip


def groups(summary: Path) -> list[tuple[str, list[Row]]]:
    cue = pd.read_csv(summary / "rq4_visual_cue_paired.csv")
    ex1 = pd.read_csv(summary / "ex1_transfer_ah_sf_paired.csv")
    ex3 = pd.read_csv(summary / "ex3_grasp_pretraining_paired.csv")
    ex4 = pd.read_csv(summary / "ex4_sf_command_paired.csv")
    sf, ah = "T3_sf_vs_rest", "T1_ah_vs_sf"
    return [
        ("Transfer from other patients: new user, three classes", transfer_rows(summary)),
        ("Mirroring left-hemiplegic patients: three classes", mirror_rows(summary)),
        ("Channels, TS+LR: finger vs rest", [
            paired(cue, "central 14 vs all 40", task=sf, comparison="central_14 vs all_40"),
            paired(cue, "parieto-occipital 5 vs all 40", task=sf,
                   comparison="parieto_occipital_5 vs all_40"),
        ]),
        ("Channels, TS+LR: hand vs finger", [
            paired(cue, "central 14 vs all 40", task=ah, comparison="central_14 vs all_40"),
            paired(cue, "parieto-occipital 5 vs all 40", task=ah,
                   comparison="parieto_occipital_5 vs all_40"),
            paired(cue, "parieto-occipital 5 vs central 14", task=ah,
                   comparison="parieto_occipital_5 vs central_14"),
        ]),
        ("EEGNet pre-trained on other patients: hand vs finger", [
            paired(ex1, "fine-tuned vs not fine-tuned",
                   comparison="B_vs_pretrained_same_alignment"),
            paired(ex1, "fine-tuned vs pre-trained, no target data",
                   comparison="B_vs_zeroshot_rest"),
            paired(ex1, "fine-tuned vs EEGNet from scratch", comparison="B"),
            paired(ex1, "fine-tuned vs TS+LR", comparison="B_vs_ts_lr"),
        ]),
        ("Healthy grasp imagery in pre-training: hand vs finger", [
            paired(ex3, "patients plus healthy grasps vs patients only", comparison="GP_vs_B"),
            paired(ex3, "healthy grasps only vs patients only", comparison="G_vs_B"),
        ]),
        ("More data per decision, TS+LR", [
            paired(ex1, "five 4 s crops vs one window, hand vs finger", comparison="A_standard"),
            paired(ex1, "crops averaged at test, hand vs finger", comparison="A_crop_mean"),
            paired(ex4, "crops vs one window, central 14, finger vs rest",
                   comparison="W_ts_lr_c14 vs ts_lr_c14"),
        ]),
        ("Raw recordings and slow waves: hand vs finger", slow_rows(summary)),
        ("Another day and acting only when sure", [
            paired(ex1, "old session added to new pool, hand vs finger", comparison="C"),
            paired(ex4, "acting when sure vs every window, finger vs rest",
                   comparison="R (ts_lr_c14) acting vs ts_lr_c14 all windows"),
        ]),
    ]  # fmt: skip


def draw(summary: Path) -> plt.Figure:
    blocks = groups(summary)
    lines: list[tuple[str, Row | None]] = []
    for title, rows in blocks:
        lines.append((title, None))
        lines.extend((row.label, row) for row in rows)
    step = 0.118  # inches per line
    fig = plt.figure(figsize=(TEXT_WIDTH_IN - 0.06, step * len(lines) + 0.55))
    left, right = 0.375, 0.75
    ax = fig.add_axes((left, 0.42 / fig.get_figheight(), right - left,
                       1 - 0.52 / fig.get_figheight()))  # fmt: skip
    lowest = min(row.lo for _, rows in blocks for row in rows)
    highest = max(row.hi for _, rows in blocks for row in rows)
    ax.set_xlim(5 * (lowest // 5) - 1, 5 * (highest // 5 + 1) + 1)
    ax.set_ylim(len(lines) - 0.4, -1.2)
    ax.axvline(0, color=CHANCE_GREY, lw=0.7, zorder=1)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.grid(axis="x", color="#ececec", lw=0.5)
    ax.set_axisbelow(True)
    ax.set_xlabel("Difference, variant minus reference (points of balanced accuracy, 95 % CI)")
    to_axes = ("axes fraction", "data")
    columns = {"variant": 1.08, "reference": 1.23, "label": 1.36}
    for name, x in columns.items():
        head = {"variant": "Variant", "reference": "Ref.", "label": "Plan"}[name]
        ax.annotate(head, (x, -1.0), xycoords=to_axes, ha="center", va="center",
                    color=SECOND_INK, annotation_clip=False)  # fmt: skip
    for y, (text, row) in enumerate(lines):
        if row is None:
            ax.annotate(text, (-left / (right - left) + 0.01, y), xycoords=to_axes, ha="left",
                        va="center", fontweight="semibold", annotation_clip=False)  # fmt: skip
            if y > 0:
                ax.axhline(y - 0.5, color="#dddddd", lw=0.5, xmin=-0.95, xmax=1.4, clip_on=False)
            continue
        ax.annotate(text, (-0.012, y), xycoords=to_axes, ha="right", va="center",
                    annotation_clip=False)  # fmt: skip
        face = MEAN_INK if row.planned else "white"
        ax.errorbar(row.diff, y, xerr=[[row.diff - row.lo], [row.hi - row.diff]], fmt="o",
                    ms=3.4, mfc=face, mec=MEAN_INK, mew=0.8, color=MEAN_INK, elinewidth=1.0,
                    capsize=0, zorder=3)  # fmt: skip
        for name, value in (("variant", row.variant), ("reference", row.reference)):
            ax.annotate(f"{value:.1f}", (columns[name], y), xycoords=to_axes, ha="center",
                        va="center", annotation_clip=False)  # fmt: skip
        ax.annotate("P" if row.planned else "X", (columns["label"], y), xycoords=to_axes,
                    ha="center", va="center", annotation_clip=False)  # fmt: skip
    return fig


def check_text_width(pdf: Path) -> float:
    box = re.search(rb"/MediaBox\s*\[\s*0 0 ([\d.]+) ([\d.]+)", pdf.read_bytes())
    if box is None:
        raise SystemExit(f"{pdf}: no page size found")
    width = float(box[1]) / 72
    if width > TEXT_WIDTH_IN + 1e-3:
        raise SystemExit(f"{pdf.name} is {width:.2f} in wide, more than the text width")
    return width


def main() -> None:
    paths = get_paths()
    summary = paths.root / "results" / "summary"
    use_paper_style(paths.root)
    fig = draw(summary)
    check_print(fig)
    save(fig, paths.figures, "paper_ablation")
    width = check_text_width(paths.figures / "paper_ablation.pdf")
    paper = paths.root / "paper" / "figures" / "paper_ablation.pdf"
    shutil.copyfile(paths.figures / "paper_ablation.pdf", paper)
    print(f"wrote {paths.figures / 'paper_ablation'}.pdf/.png ({width:.2f} in wide) and {paper}")


if __name__ == "__main__":
    main()
