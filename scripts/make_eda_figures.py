"""Regenerate every exploratory figure and the ERD table from the epoch cache.

uv run python scripts/make_eda_figures.py --session pre --out docs/figures
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import welch

from sixthfinger.config import load_data_config
from sixthfinger.data.channels import subject_group
from sixthfinger.data.epochs import load_windows
from sixthfinger.paths import get_paths
from sixthfinger.viz import topo
from sixthfinger.viz.plots import CLASS_COLORS, CLASS_SHORT, save, use_style

log = logging.getLogger("eda")
SHOW = ("C3", "Cz", "C4")
SESSIONS = ("pre", "post", "follow")
MI = {1: "affected_hand", 2: "sixth_finger"}


def sem(a: np.ndarray, axis: int = 0) -> np.ndarray:
    return a.std(axis=axis, ddof=1) / np.sqrt(a.shape[axis])


def subject_erd(cfg, paths, subject: str, session: str) -> dict:
    """Per-subject ERD maps for AH and SF, mirrored and not."""
    out = {}
    for mirror in (True, False):
        X, y = topo.cue_windows(subject, session, cfg, paths.processed, mirror=mirror)
        for label, name in MI.items():
            if (y == label).sum() < 5:
                continue
            erd, times = topo.erd_timefreq(X[y == label])
            out[(name, mirror)] = erd
            out["times"] = times
    return out


def psd_figure(cfg, paths, session: str, out: Path) -> None:
    X, md = load_windows(paths.epochs, cfg, sessions=[session], mirror=True)
    idx = [cfg.channels.keep.index(c) for c in SHOW]
    f, p = welch(X[:, idx], fs=cfg.signal.sfreq, nperseg=int(2 * cfg.signal.sfreq), axis=-1)
    db = 10 * np.log10(p)
    per_subject = {
        name: np.stack(
            [
                db[(md.subject == s).to_numpy() & (md.label_name == name).to_numpy()].mean(axis=0)
                for s in sorted(md.subject.unique())
            ]
        )
        for name in CLASS_COLORS
    }
    band = (f >= 2) & (f <= 40)
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.4), sharey=True)
    for k, (ax, ch) in enumerate(zip(axes, SHOW, strict=True)):
        for name, arr in per_subject.items():
            m, e = arr[:, k].mean(axis=0), sem(arr[:, k])
            ax.plot(f[band], m[band], color=CLASS_COLORS[name], label=CLASS_SHORT[name], lw=1)
            ax.fill_between(
                f[band], (m - e)[band], (m + e)[band], color=CLASS_COLORS[name], alpha=0.2
            )
        ax.axvspan(8, 13, color="0.9", zorder=0)
        ax.set_title(ch if ch == "Cz" else f"{ch} ({'contra' if ch == 'C3' else 'ipsi'}lateral)")
        ax.set_xlabel("Hz")
    axes[0].set_ylabel("power (dB re 1 V²/Hz)")
    axes[0].legend(frameon=False)
    fig.suptitle(
        f"Power spectra, {session} session, {len(per_subject['rest'])} subjects (mean ± SEM)",
        y=1.06,
    )
    save(fig, out, "eda_psd")


def timecourse_and_tfr(maps: dict, cfg, session: str, out: Path) -> None:
    c3 = cfg.channels.keep.index("C3")
    times = maps["times"]
    mu = (topo.TFR_FREQS >= 8) & (topo.TFR_FREQS <= 13)
    fig, ax = plt.subplots(figsize=(4.2, 2.6))
    for name in MI.values():
        curves = np.stack([m[(name, True)][c3, mu].mean(axis=0) for m in maps["subjects"].values()])
        mean, err = curves.mean(axis=0), sem(curves)
        ax.plot(times, mean, color=CLASS_COLORS[name], label=CLASS_SHORT[name])
        ax.fill_between(times, mean - err, mean + err, color=CLASS_COLORS[name], alpha=0.2)
    ax.axvline(0, color="k", lw=0.8)
    ax.axhline(0, color="0.5", lw=0.5)
    ax.axvspan(1, 5, color="0.93", zorder=0)
    ax.set_xlabel("time from imagery cue (s)")
    ax.set_ylabel("8–13 Hz ERD at C3 (%)")
    ax.set_title(f"Mu ERD, contralateral (mirrored), {session}, n = {len(curves)}")
    ax.legend(frameon=False)
    save(fig, out, "eda_erd_timecourse")

    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.6), sharey=True)
    for ax, name in zip(axes, MI.values(), strict=True):
        tfr = np.stack([m[(name, True)][c3] for m in maps["subjects"].values()]).mean(axis=0)
        im = ax.pcolormesh(
            times, topo.TFR_FREQS, tfr, cmap="RdBu_r", vmin=-40, vmax=40, shading="auto"
        )
        ax.axvline(0, color="k", lw=0.8)
        ax.set_title(f"{CLASS_SHORT[name]} at C3 (contralateral)")
        ax.set_xlabel("time from cue (s)")
    axes[0].set_ylabel("Hz")
    fig.colorbar(im, ax=axes, label="ERD/ERS (%)")
    save(fig, out, "eda_tfr")


def topomaps(maps: dict, cfg, session: str, out: Path) -> None:
    info = topo.montage_info(cfg.channels.keep)
    times = maps["times"]
    for mirror, suffix in ((True, ""), (False, "_unmirrored")):
        vals = {
            name: np.stack(
                [
                    topo.band_mean(m[(name, mirror)], times, topo.BANDS["mu"])
                    for m in maps["subjects"].values()
                ]
            ).mean(axis=0)
            for name in MI.values()
        }
        fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.6))
        panels = [
            ("AH", vals["affected_hand"]),
            ("SF", vals["sixth_finger"]),
            ("SF − AH", vals["sixth_finger"] - vals["affected_hand"]),
        ]
        for ax, (title, v) in zip(axes, panels, strict=True):
            im = topo.band_topomap(v, info, ax, title)
        fig.colorbar(im, ax=axes, label="8–13 Hz ERD, 1–5 s (%)", shrink=0.8)
        which = "mirrored: left of head = contralateral" if mirror else "not mirrored"
        fig.suptitle(f"Mu ERD topography, {session}, {which}")
        save(fig, out, f"eda_topomaps{suffix}")


def sessions_figure(all_maps: dict, cfg, out: Path) -> None:
    c3 = cfg.channels.keep.index("C3")
    mu = (topo.TFR_FREQS >= 8) & (topo.TFR_FREQS <= 13)
    fig, axes = plt.subplots(2, 3, figsize=(7.2, 4.8), sharex=True, sharey=True)
    fig.subplots_adjust(hspace=0.45)
    for i, group in enumerate(("B", "T")):
        for j, session in enumerate(SESSIONS):
            ax = axes[i, j]
            maps = all_maps[session]
            subs = [s for s in maps["subjects"] if subject_group(s) == group]
            for name in MI.values():
                curves = [
                    maps["subjects"][s][(name, True)][c3, mu].mean(axis=0)
                    for s in subs
                    if (name, True) in maps["subjects"][s]
                ]
                if len(curves) < 2:
                    continue
                curves = np.stack(curves)
                ax.plot(
                    maps["times"],
                    curves.mean(axis=0),
                    color=CLASS_COLORS[name],
                    label=CLASS_SHORT[name],
                )
                ax.fill_between(
                    maps["times"],
                    curves.mean(0) - sem(curves),
                    curves.mean(0) + sem(curves),
                    color=CLASS_COLORS[name],
                    alpha=0.2,
                )
            ax.axvline(0, color="k", lw=0.8)
            ax.axhline(0, color="0.5", lw=0.5)
            label = "BCI" if group == "B" else "conventional"
            ax.set_title(f"{label}, {session} (n = {len(subs)})", fontsize=8)
    for ax in axes[1]:
        ax.set_xlabel("time from cue (s)")
    for ax in axes[:, 0]:
        ax.set_ylabel("mu ERD at C3 (%)")
    axes[0, 0].legend(frameon=False)
    save(fig, out, "eda_sessions")


def quality_figures(cfg, paths, session: str, out: Path, flags_path: Path) -> None:
    X, md = load_windows(paths.epochs, cfg, sessions=[session])
    subjects = sorted(md.subject.unique())
    c3 = cfg.channels.keep.index("C3")
    n = len(subjects)
    cols = 6
    rows = int(np.ceil(n / cols))
    fig1, ax1 = plt.subplots(rows, cols, figsize=(7.2, 1.5 * rows), sharex=True, sharey=True)
    fig2, ax2 = plt.subplots(rows, cols, figsize=(7.2, 1.5 * rows), sharex=True, sharey=True)
    for f in (fig1, fig2):
        f.subplots_adjust(hspace=0.5)
    flags = []
    std_all = X.std(axis=-1) * 1e6  # (n, ch), microvolts
    ch_median = np.median(std_all, axis=0)
    for k, s in enumerate(subjects):
        sel = (md.subject == s).to_numpy()
        ch_std = np.median(std_all[sel], axis=0)
        logvar = np.log10(X[sel, c3].var(axis=-1))
        a, b = ax1.flat[k], ax2.flat[k]
        a.bar(range(len(ch_std)), ch_std, width=1.0, color="0.4")
        a.set_title(s, fontsize=7)
        names = md.label_name[sel].to_numpy()
        for name, color in CLASS_COLORS.items():
            at = np.flatnonzero(names == name)
            b.plot(at, logvar[at], ".", ms=1.5, color=color, label=CLASS_SHORT[name])
        b.set_title(s, fontsize=7)
        for c, v in enumerate(ch_std):
            ratio = v / ch_median[c]
            if ratio > 2.5 or ratio < 0.4:
                flags.append(
                    {
                        "subject": s,
                        "session": session,
                        "kind": "channel_std",
                        "item": cfg.channels.keep[c],
                        "value": round(float(ratio), 2),
                        "note": "median window std relative to all subjects",
                    }
                )
        z = (logvar - np.median(logvar)) / (
            1.4826 * np.median(np.abs(logvar - np.median(logvar))) + 1e-12
        )
        n_out = int((np.abs(z) > 5).sum())
        if n_out:
            flags.append(
                {
                    "subject": s,
                    "session": session,
                    "kind": "c3_window_outliers",
                    "item": "C3",
                    "value": n_out,
                    "note": "windows with |robust z| > 5 of log variance",
                }
            )
    for extra in list(ax1.flat[n:]) + list(ax2.flat[n:]):
        extra.axis("off")
    fig1.supxlabel("channel index (40 kept channels)")
    fig1.supylabel("median window SD (µV)")
    fig2.supxlabel("window in session order")
    fig2.supylabel("log10 variance at C3")
    ax2.flat[0].legend(frameon=False, fontsize=6, markerscale=3)
    save(fig1, out, "eda_quality_channels")
    save(fig2, out, "eda_quality_windows")
    cols_ = ["subject", "session", "kind", "item", "value", "note"]
    pd.DataFrame(flags, columns=cols_).to_csv(flags_path, index=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--session", default="pre", choices=SESSIONS)
    parser.add_argument("--out", type=Path, default=Path("docs/figures"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("fontTools").setLevel(logging.WARNING)
    use_style()
    cfg, paths = load_data_config(), get_paths()
    summary = paths.results / "summary"
    summary.mkdir(parents=True, exist_ok=True)

    all_maps, rows = {}, []
    for session in SESSIONS:
        maps = {"subjects": {}}
        for subject in cfg.subjects.ids:
            if session not in cfg.sessions_for(subject):
                continue
            m = subject_erd(cfg, paths, subject, session)
            if "times" not in m:
                continue
            maps["times"] = m.pop("times")
            maps["subjects"][subject] = m
            for (name, mirror), erd in m.items():
                if not mirror:
                    continue
                for band, rng in topo.BANDS.items():
                    vals = topo.band_mean(erd, maps["times"], rng)
                    for ch in SHOW:
                        rows.append(
                            {
                                "subject": subject,
                                "session": session,
                                "class": name,
                                "band": band,
                                "channel": ch,
                                "erd_percent": round(float(vals[cfg.channels.keep.index(ch)]), 2),
                            }
                        )
            log.info("%s %s done", subject, session)
        all_maps[session] = maps
    pd.DataFrame(rows).to_csv(summary / "eda_erd_values.csv", index=False)

    psd_figure(cfg, paths, args.session, args.out)
    timecourse_and_tfr(all_maps[args.session], cfg, args.session, args.out)
    topomaps(all_maps[args.session], cfg, args.session, args.out)
    sessions_figure(all_maps, cfg, args.out)
    quality_figures(cfg, paths, args.session, args.out, summary / "eda_quality_flags.csv")
    log.info("figures in %s", args.out)


if __name__ == "__main__":
    main()
