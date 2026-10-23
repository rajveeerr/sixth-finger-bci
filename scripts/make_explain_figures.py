"""P09 Study 5 (exploratory): what the decoders look at.

uv run python scripts/make_explain_figures.py
uv run python scripts/make_explain_figures.py --summary-only   # the group shares, stored values

1. CSP patterns of `csp_lda` per patient, `pre`, fitted on runs 01-02 by P06's rule (every
   window of the task's classes), AH vs SF and SF vs REST, hemisphere-mirrored so the
   affected side is on the left for everyone; each patient's map is the mean of its six
   normalised absolute patterns, the group map the mean over patients.
2. Haufe patterns of the spatial filters of the 24 pre-trained EEGNets (P07, aligned,
   unmirrored): each depthwise filter's pattern uses the covariance of the temporally filtered
   input it sees, estimated on 40 random windows of each of the model's training patients.
3. The share of each map's weight on the frontal channels (AF3, AF4, F5, F6; eye movements)
   and on the parieto-occipital ones (POz, PO3-PO6; vision), against their share of the 40
   channels (10 % and 12.5 %).
Writes results/summary/rq4_pattern_shares.csv, rq4_pattern_share_summary.csv (the mean share
of each source against the channels' share) and docs/figures/rq4_{csp,eegnet}_patterns_group.
"""

from __future__ import annotations

import argparse
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from mne.viz import plot_topomap

from sixthfinger.config import load_data_config
from sixthfinger.data.epochs import load_windows
from sixthfinger.evaluation.runner import method_params
from sixthfinger.models.deep import build_module
from sixthfinger.models.registry import Batch, make_method
from sixthfinger.paths import current_git_sha, get_paths
from sixthfinger.preprocessing.alignment import align, reference_matrix
from sixthfinger.viz.explain import (
    FRONTAL,
    PARIETO_OCCIPITAL,
    eegnet_patterns,
    normalised_abs,
    weight_share,
)
from sixthfinger.viz.plots import save, use_style
from sixthfinger.viz.topo import montage_info

TASKS = {"T1_ah_vs_sf": [1, 2], "T3_sf_vs_rest": [0, 2]}
WINDOWS_PER_PATIENT = 40


def shares(subject_map: np.ndarray, channels: list[str]) -> dict:
    return dict(frontal_share=weight_share(subject_map, channels, FRONTAL),
                parieto_occipital_share=weight_share(subject_map, channels,
                                                     PARIETO_OCCIPITAL))  # fmt: skip


def csp_maps(paths, cfg, channels) -> tuple[dict, list[dict]]:
    params = method_params("csp_lda", paths.configs)
    pre = [s for s in cfg.subjects.ids if "pre" in cfg.sessions_for(s)]
    maps, rows = {t: [] for t in TASKS}, []
    for subject in pre:
        X, md = load_windows(paths.epochs, cfg, subjects=[subject], sessions=["pre"], mirror=True)
        md = md.reset_index(drop=True)
        for task, classes in TASKS.items():
            train = md[md.label.isin(classes) & md.run.isin([1, 2])]
            m = make_method("csp_lda", n_classes=2, **params)
            m.fit(Batch(X[train.index], train.label.to_numpy(), train))
            csp = m.pipe[0]
            subject_map = normalised_abs(csp.patterns_[: csp.n_components]).mean(axis=0)
            maps[task].append(subject_map)
            rows.append(dict(source=f"csp_{task}", unit=subject, **shares(subject_map, channels)))
    return {t: np.mean(v, axis=0) for t, v in maps.items()}, rows


def sample_windows(paths, cfg) -> tuple[np.ndarray, np.ndarray]:
    """40 random windows of every patient, aligned by the patient's own reference (all of its
    windows, as in the pre-training), in the network's input units."""
    deep = method_params("eegnet_ea_ft", paths.configs)
    rng = np.random.default_rng(0)
    xs, subj = [], []
    for subject in cfg.subjects.ids:
        X, _ = load_windows(paths.epochs, cfg, subjects=[subject])
        R = reference_matrix(X, deep["alignment"]["rel_floor"])
        pick = rng.choice(len(X), size=min(WINDOWS_PER_PATIENT, len(X)), replace=False)
        xs.append(align(X[np.sort(pick)], R) * np.float32(deep["input_scale"]))
        subj += [subject] * len(pick)
    return np.concatenate(xs), np.array(subj)


def eegnet_maps(paths, cfg, channels) -> tuple[np.ndarray, list[dict]]:
    deep = method_params("eegnet_ea_ft", paths.configs)
    models = paths.models / "pretrained"
    manifest = json.loads((models / "manifest.json").read_text())
    X, subj = sample_windows(paths, cfg)
    maps, rows = [], []
    for name, entry in sorted(manifest.items()):
        if entry.get("permuted") or entry.get("mirror"):
            continue
        net = build_module(deep, X.shape[1], 3, X.shape[2])
        net.load_state_dict(torch.load(models / name, weights_only=True, map_location="cpu"))
        rows_of = np.isin(subj, entry["train_subjects"])
        patterns = eegnet_patterns(net, X[rows_of])
        model_map = normalised_abs(patterns).mean(axis=0)
        maps.append(model_map)
        rows.append(dict(source="eegnet_pretrained", unit=entry["target"],
                         **shares(model_map, channels)))  # fmt: skip
    return np.mean(maps, axis=0), rows


def share_summary(shares_: pd.DataFrame, channels: list[str]) -> pd.DataFrame:
    """Each source's mean share over its patients or models, next to the channels' own share."""
    g = shares_.groupby("source", sort=False)
    out = g[["frontal_share", "parieto_occipital_share"]].mean().add_suffix("_mean")
    out.insert(0, "n", g.size())
    out["frontal_channel_share"] = len(FRONTAL) / len(channels)
    out["parieto_occipital_channel_share"] = len(PARIETO_OCCIPITAL) / len(channels)
    return out.reset_index()


def topomaps(maps: dict, info, title: str, name: str, figures) -> None:
    """Each map on its own range (lowest to highest channel), no colour beyond the electrodes."""
    fig, axes = plt.subplots(1, len(maps), figsize=(2.4 * len(maps), 2.6), squeeze=False)
    for ax, (label, m) in zip(axes[0], maps.items(), strict=True):
        im, _ = plot_topomap(m, info, axes=ax, show=False, cmap="Reds", contours=4,
                             vlim=(m.min(), m.max()), extrapolate="local")  # fmt: skip
        ax.set_title(label, fontsize=8)
        bar = fig.colorbar(im, ax=ax, shrink=0.6, ticks=[m.min(), m.max()])
        bar.ax.set_yticklabels(["lowest", "highest"], fontsize=6)
    fig.suptitle(title, fontsize=8)
    save(fig, figures, name)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--summary-only", action="store_true")
    args = ap.parse_args()
    paths, cfg = get_paths(), load_data_config()
    channels = list(cfg.channels.keep)
    summary = paths.results / "summary"
    if args.summary_only:
        stored = pd.read_csv(summary / "rq4_pattern_shares.csv")
        share_summary(stored, channels).to_csv(summary / "rq4_pattern_share_summary.csv",
                                               index=False, float_format="%.6g")  # fmt: skip
        return
    info = montage_info(channels, cfg.signal.sfreq)
    use_style()
    csp, rows = csp_maps(paths, cfg, channels)
    eeg, eeg_rows = eegnet_maps(paths, cfg, channels)
    out = pd.DataFrame(rows + eeg_rows).assign(git_sha=current_git_sha())
    out.to_csv(summary / "rq4_pattern_shares.csv", index=False, float_format="%.6g")
    share_summary(out, channels).to_csv(summary / "rq4_pattern_share_summary.csv", index=False,
                                        float_format="%.6g")  # fmt: skip
    print(out.groupby("source")[["frontal_share", "parieto_occipital_share"]].agg(["mean", "max"]))
    maps = pd.DataFrame(
        {
            "channel": channels,
            "csp_T1_ah_vs_sf": csp["T1_ah_vs_sf"],
            "csp_T3_sf_vs_rest": csp["T3_sf_vs_rest"],
            "eegnet_pretrained": eeg,
        }
    )
    maps.to_csv(paths.results / "summary" / "rq4_pattern_maps.csv", index=False,
                float_format="%.6g")  # fmt: skip
    topomaps({"AH vs SF": csp["T1_ah_vs_sf"], "SF vs REST": csp["T3_sf_vs_rest"]}, info,
             "CSP patterns, mean over 22 patients (pre, runs 01-02, mirrored)",
             "rq4_csp_patterns_group", paths.figures)  # fmt: skip
    topomaps({"EEGNet spatial patterns": eeg}, info,
             "Haufe patterns, mean over the 24 pre-trained models (21 distinct)",
             "rq4_eegnet_patterns_group", paths.figures)  # fmt: skip


if __name__ == "__main__":
    main()
