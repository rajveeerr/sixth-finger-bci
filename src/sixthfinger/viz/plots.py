"""Result figures: shared style, save helper, learning curves, benchmark bars."""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

CLASS_COLORS = {"rest": "#7f7f7f", "affected_hand": "#1f77b4", "sixth_finger": "#d62728"}
CLASS_SHORT = {"rest": "REST", "affected_hand": "AH", "sixth_finger": "SF"}
ACCENT = "#1f77b4"
SUBJECT_GREY = "#b8b8b8"
REFERENCE_GREY = "#6f6f6f"
PROTOCOL_LABELS = {
    "paper_replica": "replica",
    "cv_leakfree": "CV leak-free",
    "loro": "leave-run-out",
    "chrono": "chronological",
}


def use_style() -> None:
    # Type 42 embeds TrueType fonts, which IEEE's PDF checks require.
    mpl.rcParams.update(
        {
            "figure.dpi": 120,
            "savefig.dpi": 300,
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "pdf.fonttype": 42,
        }
    )


def save(fig: plt.Figure, out_dir: Path, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    # No creation date, so re-running a script leaves an unchanged figure unchanged in git.
    fig.savefig(out_dir / f"{name}.pdf", bbox_inches="tight", metadata={"CreationDate": None})
    fig.savefig(out_dir / f"{name}.png", bbox_inches="tight")
    plt.close(fig)


def reference_line(ax: plt.Axes, y: float, label: str) -> None:
    ax.axhline(y, color=REFERENCE_GREY, lw=0.8, zorder=1)
    ax.annotate(
        label,
        (1, y),
        xycoords=("axes fraction", "data"),
        xytext=(-2, -2),
        textcoords="offset points",
        ha="right",
        va="top",
        fontsize=7,
        color=REFERENCE_GREY,
    )


def protocol_lines(
    ax: plt.Axes,
    wide: pd.DataFrame,
    protocols: list[str],
    title: str,
    chance: float,
    ci: pd.DataFrame | None = None,
    not_comparable: dict[str, str] | None = None,
) -> None:
    """One thin grey line per subject across the protocols, the group mean on top.

    wide: rows = subjects, columns = protocols, balanced accuracy. ci: optional rows =
    protocols with columns ci_lo, ci_hi for the mean. not_comparable: protocols left blank
    with a note, for a dataset where they do not measure the same thing.
    """
    x = np.arange(len(protocols))
    blank = list(not_comparable or {})
    wide = wide.reindex(columns=protocols).copy()
    wide[blank] = np.nan
    if ci is not None:
        ci = ci.copy()
        ci.loc[[p for p in blank if p in ci.index], ["ci_lo", "ci_hi"]] = np.nan
    for _, row in wide[protocols].iterrows():
        ax.plot(x, row.to_numpy(), color=SUBJECT_GREY, lw=0.8, alpha=0.8, zorder=2)
    mean = wide[protocols].mean()
    ax.plot(x, mean.to_numpy(), color=ACCENT, lw=2, marker="o", ms=5, zorder=4)
    if ci is not None:
        lo = mean - ci.loc[protocols, "ci_lo"]
        hi = ci.loc[protocols, "ci_hi"] - mean
        ax.errorbar(x, mean, yerr=[lo, hi], fmt="none", ecolor=ACCENT, lw=1.2, zorder=3)
    reference_line(ax, chance, "chance")
    ax.set_xticks(x, [PROTOCOL_LABELS.get(p, p) for p in protocols], rotation=20, ha="right")
    ax.set_title(f"{title} (n = {len(wide)})", fontsize=8)
    if not_comparable:
        ax.text(
            0.98,
            0.04,
            "\n".join(not_comparable.values()),
            transform=ax.transAxes,
            fontsize=6,
            color="#6f6f6f",
            ha="right",
            va="bottom",
        )
    ax.grid(axis="y", color="#e6e6e6", lw=0.6)
    ax.set_axisbelow(True)


def learning_curve(*args, **kwargs):
    raise NotImplementedError("Implemented in phase P06.")
