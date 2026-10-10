import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sixthfinger.viz.plots import save


def test_saved_figures_are_byte_identical_across_runs(tmp_path):
    def draw(out):
        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1])
        save(fig, out, "f")

    draw(tmp_path / "a")
    time.sleep(1.1)  # a creation date would now differ
    draw(tmp_path / "b")
    for ext in ("pdf", "png"):
        assert (tmp_path / "a" / f"f.{ext}").read_bytes() == (
            tmp_path / "b" / f"f.{ext}"
        ).read_bytes()
