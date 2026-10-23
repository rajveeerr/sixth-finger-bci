"""Result figures: shared style, save helper, learning curves, benchmark bars."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from matplotlib.text import Text

CLASS_COLORS = {"rest": "#7f7f7f", "affected_hand": "#1f77b4", "sixth_finger": "#d62728"}
CLASS_SHORT = {"rest": "REST", "affected_hand": "AH", "sixth_finger": "SF"}
ACCENT = "#1f77b4"
SUBJECT_GREY = "#b8b8b8"
REFERENCE_GREY = "#6f6f6f"
# The paper's figures: the web drawings' typeface and greys, IEEE's 7 pt minimum and column.
PAPER_PT = 7
PAPER_COLUMN_IN = 3.5
PATIENT_GREY = "#c8c8c8"
MEAN_INK = "#1a1a1a"
SECOND_INK = "#7a7a7a"
CHANCE_GREY = "#8c8c8c"
INTER_WOFF2 = Path(
    "web/node_modules/@fontsource-variable/inter/files/inter-latin-wght-normal.woff2"
)
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


def _static_inter(woff2: Path, weights: tuple[int, ...] = (400, 600)) -> list[Path]:
    """Static Inter TrueType fonts cut from the page's variable font, cached in the temp folder."""
    out_dir = Path(tempfile.gettempdir()) / "sixth-finger-paper-fonts"
    paths = [out_dir / f"inter-{w}.ttf" for w in weights]
    if all(p.exists() for p in paths):
        return paths
    if not woff2.exists():
        raise SystemExit(f"{woff2} is missing: run npm --prefix web ci first")
    try:
        import brotli  # noqa: F401  (fontTools needs it to read woff2)
    except ImportError as err:
        raise SystemExit(
            "reading the web font needs brotli: uv run --with brotli==1.2.1 ..."
        ) from err
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont

    out_dir.mkdir(parents=True, exist_ok=True)
    for weight, path in zip(weights, paths, strict=True):
        font = instantiateVariableFont(TTFont(woff2), {"wght": weight})
        font.flavor = None
        for record in font["name"].names:
            if record.nameID in (4, 6):
                record.string = f"Inter-{weight}"
        font.save(path)
    return paths


def use_paper_style(root: Path) -> None:
    """The paper's figures: Inter at 7 pt, thin dark axes, TrueType embedded."""
    use_style()
    family = None
    for path in _static_inter(root / INTER_WOFF2):
        font_manager.fontManager.addfont(str(path))
        family = font_manager.FontProperties(fname=str(path)).get_name()
    mpl.rcParams.update(
        {
            "font.family": family,
            "font.size": PAPER_PT,
            "axes.titlesize": PAPER_PT,
            "axes.labelsize": PAPER_PT,
            "xtick.labelsize": PAPER_PT,
            "ytick.labelsize": PAPER_PT,
            "legend.fontsize": PAPER_PT,
            "axes.linewidth": 0.6,
            "axes.edgecolor": "#4d4d4d",
            "axes.labelcolor": MEAN_INK,
            "text.color": MEAN_INK,
            "xtick.color": "#4d4d4d",
            "ytick.color": "#4d4d4d",
            "xtick.major.width": 0.6,
            "ytick.major.width": 0.6,
            "xtick.major.size": 2,
            "ytick.major.size": 2,
            "xtick.major.pad": 2,
            "ytick.major.pad": 2,
            "axes.labelpad": 2,
            "axes.titlepad": 4,
        }
    )


def check_print(fig: plt.Figure) -> None:
    """Refuse a figure with any visible text under the paper's 7 pt."""
    small = [
        (t.get_text(), t.get_fontsize())
        for t in fig.findobj(Text)
        if t.get_visible() and t.get_text().strip() and t.get_fontsize() < PAPER_PT
    ]
    if small:
        raise SystemExit(f"text under {PAPER_PT} pt: {small}")


def check_width(pdf: Path) -> float:
    """The saved PDF's width in inches; more than one IEEE column is refused."""
    box = re.search(rb"/MediaBox\s*\[\s*0 0 ([\d.]+) ([\d.]+)", pdf.read_bytes())
    if box is None:
        raise SystemExit(f"{pdf}: no page size found")
    width = float(box[1]) / 72
    if width > PAPER_COLUMN_IN + 1e-3:
        raise SystemExit(f"{pdf.name} is {width:.2f} in wide, more than one column")
    return width


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
