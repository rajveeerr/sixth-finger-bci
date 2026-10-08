"""CSP patterns of csp_lda for one development subject, for the presentation (P06 step 4.6).

uv run python scripts/rq1_csp_patterns.py --subject sub-01

The registry pipeline is fitted on the chrono training runs (01-02) of session pre, AH vs
SF, and its CSP patterns (not filters) are drawn as topographies.
"""

from __future__ import annotations

import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from mne.viz import plot_topomap

from sixthfinger.config import load_data_config, load_protocol_config
from sixthfinger.data.epochs import load_windows
from sixthfinger.evaluation.runner import method_params
from sixthfinger.evaluation.splits import chrono_split
from sixthfinger.models.registry import Batch, make_method
from sixthfinger.paths import get_paths
from sixthfinger.viz.plots import save, use_style
from sixthfinger.viz.topo import montage_info

METHOD = "csp_lda"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--subject", default="sub-01")
    ap.add_argument("--session", default="pre")
    args = ap.parse_args()
    paths, data_cfg, proto = get_paths(), load_data_config(), load_protocol_config()
    classes = sorted(data_cfg.label_by_name[n].id for n in proto.tasks["T1_ah_vs_sf"])
    X, md = load_windows(
        paths.epochs, data_cfg, subjects=[args.subject], sessions=[args.session], labels=classes
    )
    ws = proto.within_session
    train, _ = chrono_split(md, ws.chrono_train_runs, ws.chrono_test_runs)
    method = make_method(METHOD, n_classes=2, **method_params(METHOD, paths.configs))
    method.fit(Batch(X[train], md.label.to_numpy()[train], md.iloc[train]))
    csp = method.pipe[0]
    info = montage_info(data_cfg.channels.keep, data_cfg.signal.sfreq)

    use_style()
    n = csp.n_components
    fig, axes = plt.subplots(1, n, figsize=(1.3 * n, 1.6))
    # Patterns are in volts per unit of component signal; only their shape is read, so
    # each map is scaled to its own largest absolute value.
    patterns = csp.patterns_[:n]
    patterns = patterns / np.abs(patterns).max(axis=1, keepdims=True)
    for i, (ax, pattern) in enumerate(zip(axes, patterns, strict=True)):
        plot_topomap(pattern, info, axes=ax, show=False, cmap="RdBu_r", vlim=(-1, 1), contours=0)
        ax.set_title(f"CSP {i + 1}", fontsize=8)
    fig.suptitle(
        f"{args.subject} {args.session}, AH vs SF: CSP patterns fitted on runs "
        f"{'-'.join(ws.chrono_train_runs)} ({len(train)} windows)",
        fontsize=8,
    )
    save(fig, paths.figures, f"rq1_csp_patterns_{args.subject}")


if __name__ == "__main__":
    main()
