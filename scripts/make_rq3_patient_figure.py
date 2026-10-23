"""Draw RQ3 patient by patient: adding the sixth-finger command with and without transfer (P13).

uv run python scripts/make_rq3_patient_figure.py

Reads the stored per-patient values of the confirmatory RQ3 tests on the pre-therapy session
(random draws, all patients) and draws nothing that is not in them:
- H3a and H3b: each patient's ALC with transfer (rct_tslr) minus from scratch (ts_lr), sixth
  finger against rest and three classes (results/summary/calib_alc_subject_values.csv);
- H3c: each patient's balanced accuracy, sixth finger against rest, of transfer at k = 2 and
  k = 5 minus the own-hand decoder (ah_proxy), from results/summary/calib_subject_values.csv
  exactly as summarise_calibration.py pairs them;
- the mean and 95 % bootstrap CI of each test from results/summary/calib_confirmatory.csv.
Every per-patient mean must equal its test's mean difference, or nothing is drawn.

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
from sixthfinger.viz.plots import ACCENT, save, use_style

S2, T3 = "S2_new_command", "T3_sf_vs_rest"
NAME = "rq3_patients"
DOT = "#4d4d4d"
TEXT_PT = 7


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


def strip(ax, x: float, diffs: pd.Series, test: pd.Series, rng) -> None:
    ax.scatter(x - 0.1 + rng.uniform(-0.1, 0.1, len(diffs)), diffs, s=7, color=DOT, lw=0,
               alpha=0.85, zorder=3)  # fmt: skip
    lo, hi = test.mean_diff - test.ci_lo, test.ci_hi - test.mean_diff
    ax.errorbar(x + 0.2, test.mean_diff, yerr=[[lo], [hi]], fmt="o", ms=3.5, color=ACCENT,
                elinewidth=1.2, capsize=0, zorder=4)  # fmt: skip


def figure(values: dict[str, pd.Series], stats: pd.DataFrame, out) -> None:
    use_style()
    fig, axes = plt.subplots(1, 2, figsize=(3.36, 1.9))
    rng = np.random.default_rng(0)  # horizontal jitter of the dots only
    panels = [
        ("Transfer \N{MINUS SIGN} from scratch", "ALC difference", None,
         [("H3a", "finger\nvs rest"), ("H3b", "three\nclasses")]),
        ("Transfer \N{MINUS SIGN} own-hand", "accuracy difference", "finger vs rest",
         [("H3c_k2", "$k$ = 2"), ("H3c_k5", "$k$ = 5")]),
    ]  # fmt: skip
    for ax, (title, ylabel, xlabel, strips) in zip(axes, panels, strict=True):
        ax.axhline(0, color="#6f6f6f", lw=0.8, zorder=1)
        for x, (hyp, _) in enumerate(strips):
            strip(ax, x, values[hyp], stats.loc[hyp], rng)
        ax.set_xticks(range(len(strips)), [label for _, label in strips])
        ax.set_xlim(-0.55, len(strips) - 0.45)
        ax.set_title(title, fontsize=TEXT_PT, pad=4)
        ax.set_ylabel(ylabel, fontsize=TEXT_PT, labelpad=2)
        if xlabel:
            ax.set_xlabel(xlabel, fontsize=TEXT_PT, labelpad=1)
        ax.tick_params(labelsize=TEXT_PT, length=2, pad=2)
        ax.grid(axis="y", color="#e6e6e6", lw=0.6)
        ax.set_axisbelow(True)
    fig.tight_layout(pad=0.2, w_pad=1.2)
    save(fig, out, NAME)


def main() -> None:
    paths = get_paths()
    summary = paths.root / "results" / "summary"
    values, stats = per_patient(summary), tests(summary)
    for hyp, diffs in values.items():
        test = stats.loc[hyp]
        if len(diffs) != test.n or abs(diffs.mean() - test.mean_diff) > 1e-6:
            raise SystemExit(f"{hyp}: per-patient values do not give the test's mean difference")
    figure(values, stats, paths.figures)
    paper = paths.root / "paper" / "figures" / f"{NAME}.pdf"
    shutil.copyfile(paths.figures / f"{NAME}.pdf", paper)
    print(f"wrote {paths.figures / NAME}.pdf/.png and {paper}")


if __name__ == "__main__":
    main()
