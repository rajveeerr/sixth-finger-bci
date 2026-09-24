"""Result figures: shared style, save helper, learning curves, benchmark bars."""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt

CLASS_COLORS = {"rest": "#7f7f7f", "affected_hand": "#1f77b4", "sixth_finger": "#d62728"}
CLASS_SHORT = {"rest": "REST", "affected_hand": "AH", "sixth_finger": "SF"}


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
    fig.savefig(out_dir / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(out_dir / f"{name}.png", bbox_inches="tight")
    plt.close(fig)


def learning_curve(*args, **kwargs):
    raise NotImplementedError("Implemented in phase P06.")
