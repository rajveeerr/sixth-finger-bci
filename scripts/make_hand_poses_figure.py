"""The hand in its three poses, side by side (docs/figures/hand_poses.png).

(cd web && npx playwright test e2e/poses.spec.ts)
uv run python scripts/make_hand_poses_figure.py
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sixthfinger.paths import get_paths

POSES = [
    ("IDLE", "Rest"),
    ("HAND_GRASP", "Affected hand"),
    ("SIXTH_FINGER_FLEX", "Sixth finger"),
]


def main() -> None:
    root = get_paths().root
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 4.2))
    for ax, (command, label) in zip(axes, POSES, strict=True):
        image = plt.imread(root / "web" / "test-results" / f"hand-iso-{command}.png")
        ax.imshow(image[4:-4, 4:-4])  # without the plate's hairline at the edges
        ax.set_title(f"{label}\n{command}", fontsize=10, family="monospace")
        ax.axis("off")
    fig.tight_layout()
    out = root / "docs" / "figures" / "hand_poses.png"
    fig.savefig(out, dpi=200, facecolor="white")
    print(f"wrote {out.relative_to(root)}")


if __name__ == "__main__":
    main()
