"""Draw RQ3 patient by patient: adding the sixth-finger command with and without transfer (P13).

uv run --with brotli==1.2.1 python scripts/make_rq3_patient_figure.py

Reads the stored per-patient values of the confirmatory RQ3 tests on the pre-therapy session
(random draws, all patients) and draws nothing that is not in them:
- H3a and H3b: each patient's ALC with transfer (rct_tslr) minus from scratch (ts_lr), sixth
  finger against rest and three classes (results/summary/calib_alc_subject_values.csv);
- H3c: each patient's balanced accuracy, sixth finger against rest, of transfer at k = 2 and
  k = 5 minus the own-hand decoder (ah_proxy), from results/summary/calib_subject_values.csv
  exactly as summarise_calibration.py pairs them;
- the mean and 95 % bootstrap CI of each test from results/summary/calib_confirmatory.csv.
Every per-patient mean must equal its test's mean difference, or nothing is drawn.

H3c is drawn in percentage points of balanced accuracy, H3a and H3b on the ALC scale. The style
is the paper's (scripts/make_paper_figures.py: Inter, greys; brotli cuts the font once).

Writes docs/figures/rq3_patients.{pdf,png}, sized for one IEEE column (3.5 in, text at 7 pt or
more), and copies the PDF to paper/figures/rq3_patients.pdf.
"""

from __future__ import annotations

import shutil

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from sixthfinger.paths import get_paths
from sixthfinger.viz.plots import (
    MEAN_INK,
    PATIENT_GREY,
    check_print,
    check_width,
    save,
    use_paper_style,
)

S2, T3 = "S2_new_command", "T3_sf_vs_rest"
NAME = "rq3_patients"


def per_patient(summary) -> dict[str, pd.Series]:
    """Each patient's difference in the four RQ3 tests, keyed by hypothesis."""
    alc = pd.read_csv(summary / "calib_alc_subject_values.csv")
    alc = alc[alc.role == "confirmatory"]
    out = {h: alc[alc.hypothesis == h].set_index("subject")["diff"] for h in ("H3a", "H3b")}
    values = pd.read_csv(summary / "calib_subject_values.csv")
    s2 = values[(values.scenario == S2) & (values.task == T3) & (values.session == "pre")]
    for k in (2, 5):
        at_k = s2[s2.k == k].pivot_table(index="subject", columns="method", values="bal_acc")
        out[f"H3c_k{k}"] = (at_k.rct_tslr - at_k.ah_proxy).dropna()
    return out


def tests(summary) -> pd.DataFrame:
    table = pd.read_csv(summary / "calib_confirmatory.csv")
    keep = (
        (table.role == "confirmatory")
        & (table.session == "pre")
        & (table.population == "all")
        & (table.draw_basis == "random")
        & table.hypothesis.isin(["H3a", "H3b", "H3c_k2", "H3c_k5"])
    )
    return table[keep].set_index("hypothesis")


def strip(ax, x: float, diffs: pd.Series, test: pd.Series, rng, scale: float) -> None:
    ax.scatter(x - 0.1 + rng.uniform(-0.1, 0.1, len(diffs)), scale * diffs, s=6,
               color=PATIENT_GREY, lw=0, zorder=3)  # fmt: skip
    mean, lo, hi = (scale * v for v in (test.mean_diff, test.ci_lo, test.ci_hi))
    ax.errorbar(x + 0.2, mean, yerr=[[mean - lo], [hi - mean]], fmt="o", ms=3.2,
                color=MEAN_INK, elinewidth=1.1, capsize=0, zorder=4)  # fmt: skip


def figure(values: dict[str, pd.Series], stats: pd.DataFrame, root, out) -> None:
    use_paper_style(root)
    fig, axes = plt.subplots(1, 2, figsize=(3.28, 1.95))
    rng = np.random.default_rng(0)  # horizontal jitter of the dots only
    panels = [
        ("Transfer \N{MINUS SIGN} from scratch", "ALC difference", None, 1.0,
         [("H3a", "finger\nvs rest"), ("H3b", "three\nclasses")]),
        ("Transfer \N{MINUS SIGN} own-hand", "Accuracy difference (points)", "finger vs rest",
         100.0, [("H3c_k2", "k = 2"), ("H3c_k5", "k = 5")]),
    ]  # fmt: skip
    for ax, (title, ylabel, xlabel, scale, strips) in zip(axes, panels, strict=True):
        ax.axhline(0, color="#6f6f6f", lw=0.7, zorder=1)
        for x, (hyp, _) in enumerate(strips):
            strip(ax, x, values[hyp], stats.loc[hyp], rng, scale)
        ax.set_xticks(range(len(strips)), [label for _, label in strips])
        ax.set_xlim(-0.55, len(strips) - 0.45)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        if xlabel:
            ax.set_xlabel(xlabel, labelpad=1)
        ax.grid(axis="y", color="#ececec", lw=0.5)
        ax.set_axisbelow(True)
    fig.tight_layout(pad=0.2, w_pad=1.2)
    check_print(fig)
    save(fig, out, NAME)
    check_width(out / f"{NAME}.pdf")


def main() -> None:
    paths = get_paths()
    summary = paths.root / "results" / "summary"
    values, stats = per_patient(summary), tests(summary)
    for hyp, diffs in values.items():
        test = stats.loc[hyp]
        if len(diffs) != test.n or abs(diffs.mean() - test.mean_diff) > 1e-6:
            raise SystemExit(f"{hyp}: per-patient values do not give the test's mean difference")
    figure(values, stats, paths.root, paths.figures)
    paper = paths.root / "paper" / "figures" / f"{NAME}.pdf"
    shutil.copyfile(paths.figures / f"{NAME}.pdf", paper)
    print(f"wrote {paths.figures / NAME}.pdf/.png and {paper}")


if __name__ == "__main__":
    main()
