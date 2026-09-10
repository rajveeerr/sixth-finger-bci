"""Draw the 40 analysis electrodes on a head outline (docs/figures/montage_40.{pdf,png})."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mne
import numpy as np
from matplotlib.patches import Circle, Polygon

from sixthfinger.data.channels import CHANNELS_40

SENSORIMOTOR = {
    "FC3",
    "FC1",
    "FCz",
    "FC2",
    "FC4",
    "C5",
    "C3",
    "C1",
    "Cz",
    "C2",
    "C4",
    "C6",
    "CP3",
    "CP1",
    "CPz",
    "CP2",
    "CP4",
}


def projected_positions() -> dict[str, np.ndarray]:
    """Azimuthal equidistant projection of the template positions (top view, nose up)."""
    pos = mne.channels.make_standard_montage("colin27_1005").get_positions()["ch_pos"]
    out = {}
    for name in CHANNELS_40:
        x, y, z = pos[name] / np.linalg.norm(pos[name])
        theta = np.arccos(np.clip(z, -1, 1))
        phi = np.arctan2(y, x)
        out[name] = theta * np.array([np.cos(phi), np.sin(phi)])
    return out


def main(out_dir: Path = Path("docs/figures")) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    xy = projected_positions()
    radius = np.pi / 2 * 1.02
    fig, ax = plt.subplots(figsize=(4.4, 4.6))
    ax.add_patch(Circle((0, 0), radius, fill=False, lw=1.2))
    ax.add_patch(
        Polygon(
            [[-0.18, radius * 0.995], [0, radius * 1.13], [0.18, radius * 0.995]],
            closed=False,
            fill=False,
            lw=1.2,
        )
    )
    for side in (-1, 1):
        ax.add_patch(
            Polygon(
                [
                    [side * radius, 0.22],
                    [side * radius * 1.07, 0.15],
                    [side * radius * 1.07, -0.18],
                    [side * radius, -0.25],
                ],
                closed=False,
                fill=False,
                lw=1.2,
            )
        )
    for name, (x, y) in xy.items():
        motor = name in SENSORIMOTOR
        ax.add_patch(
            Circle(
                (x, y),
                0.105,
                facecolor="#0072B2" if motor else "#E5E7EB",
                edgecolor="#1F2937",
                lw=0.6,
            )
        )
        ax.text(
            x,
            y,
            name,
            ha="center",
            va="center",
            fontsize=4.8,
            color="white" if motor else "#111827",
            fontweight="bold" if motor else "normal",
        )
    ax.set_xlim(-1.9, 1.9)
    ax.set_ylim(-1.85, 2.0)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.text(0, -1.78, "blue: sensorimotor channels used for ERD plots", ha="center", fontsize=6.5)
    for ext in ("pdf", "png"):
        fig.savefig(out_dir / f"montage_40.{ext}", bbox_inches="tight", dpi=300)
    plt.close(fig)


if __name__ == "__main__":
    main()
