"""P09 Study 4 (exploratory): replay the test runs of every `pre` session through the demo's
command gate.

uv run python scripts/pseudo_online.py --subjects sub-01 sub-03   # the development subjects
uv run python scripts/pseudo_online.py                            # everyone else
uv run python scripts/pseudo_online.py --summarise                # tables and figure

Each decoder is fitted by the P08 runner itself (configs/experiments/rq4_pseudo_online.yaml:
S1, three-class, k = all). The classical decoders' trial-locked rows equal P08's `rq2_calib_s1`
rows; rct_tslr and EEGNet refits differ from them by up to 0.0175 and 0.0735 across machines
(results/summary/rq4_pseudo_online_repro.csv). A
hook then replays runs 03-04 as continuous signals (protocol §6b, `evaluation/pseudo_online`)
and writes one file per subject and method under results/runs/rq4_pseudo_online/replay/.
A resumed run skips fitted units, and their replay files stay. sub-01 and sub-03 are flagged
in every table (gate provenance, protocol §6b). The summary also writes, from the stored replays
and the runs' lengths and cuts, rq4_pseudo_online_details.csv (per method: patients reaching
half of their periods, false activations early in a rest period, and the rates again with each
period stopped at the next one and at its first cut) and rq4_pseudo_online_replay.json (windows
kept, periods that overlap or hold a cut, the spacing of the trials, a gate that never fires).
"""

from __future__ import annotations

import argparse
import json
import logging

import numpy as np
import pandas as pd

from sixthfinger.config import load_data_config, load_protocol_config
from sixthfinger.data.epochs import run_signal
from sixthfinger.data.loading import list_processed_runs, read_eeglab_mat
from sixthfinger.evaluation import pseudo_online as po
from sixthfinger.evaluation.runner import load_experiment, run_experiment
from sixthfinger.evaluation.stats import bootstrap_ci
from sixthfinger.paths import current_git_sha, get_paths

log = logging.getLogger("pseudo_online")
EXPERIMENT = "rq4_pseudo_online"
FLAGGED = ("sub-01", "sub-03")
SFREQ = 250.0  # the processed runs' rate; run_signal refuses any other
METHOD_ORDER = ["csp_lda", "ts_lr", "rct_tslr", "eegnet_scratch"]
EARLY_S = 2.0  # a false activation this soon after a rest period starts may answer the cue before
RATES = ["sf_detection_rate", "ah_detection_rate", "ah_as_sf_rate", "false_per_minute"]


def replay_dir():
    return get_paths().runs / EXPERIMENT / "replay"


def make_hook(gate_cls):
    paths, data_cfg, proto = get_paths(), load_data_config(), load_protocol_config()
    files = {
        (r.subject, r.session, int(r.run)): r.path for r in list_processed_runs(paths.processed)
    }
    cfg = paths.configs / "experiments" / f"{EXPERIMENT}.yaml"
    exp = load_experiment(cfg, proto)
    test_runs = po.replayed_runs(exp.test_runs or proto.calibration.test_runs,
                                 exp.pool_runs or proto.calibration.pool_runs)  # fmt: skip
    n_window, sha = data_cfg.n_times, current_git_sha()
    out = replay_dir()
    out.mkdir(parents=True, exist_ok=True)

    def hook(key: dict, method) -> None:
        subject, session, name = key["subject"], key["session"], key["method"]
        replays, timeline, scored = [], [], []
        for run in test_runs:
            path = files.get((subject, session, run))
            if path is None or data_cfg.is_run_excluded(subject, session, f"{run:02d}"):
                continue
            data, rec = run_signal(path, data_cfg)
            events = (rec.event_codes, rec.event_samples, rec.sfreq)
            replayed, tl = po.replay_run(method.predict_proba, data, *events, n_window, gate_cls)
            replays.append(replayed)
            timeline.append(tl.assign(run=run))
            per = replayed.periods
            scored.append(per.assign(run=run, t0=per.start / rec.sfreq, t1=per.stop / rec.sfreq))
        row = dict(subject=subject, session=session, method=name, n_runs=len(replays),
                   flagged=subject in FLAGGED, **po.subject_metrics(replays),
                   git_sha=sha)  # fmt: skip
        stem = out / f"{subject}_{name}"
        pd.DataFrame([row]).to_parquet(f"{stem}_metrics.parquet", index=False)
        pd.concat(timeline).to_parquet(f"{stem}_timeline.parquet", index=False)
        pd.concat(scored).to_parquet(f"{stem}_periods.parquet", index=False)
        log.info("%s %s: SF %.2f, false/min %.2f", subject, name, row["sf_detection_rate"],
                 row["false_per_minute"])  # fmt: skip

    return hook


def reproduction(paths) -> pd.DataFrame:
    """Trial-locked rows of this run against P08's rq2_calib_s1 rows of the same units."""
    ours = pd.read_parquet(paths.runs / EXPERIMENT / "scores.parquet")
    p08 = pd.read_parquet(paths.runs / "rq2_calib_s1" / "scores.parquet")
    keys = ["scenario", "task", "method", "subject", "session", "k", "draw"]
    for f in (ours, p08):
        f["k"] = f["k"].astype(int)
    m = ours.merge(p08, on=keys, suffixes=("", "_p08"))
    m["diff"] = (m.bal_acc - m.bal_acc_p08).abs()
    return m.groupby("method").agg(n=("diff", "size"), max_abs_diff=("diff", "max")).reset_index()


def demo_subject(paths) -> str:
    """The demo patient by protocol §10 with the tie-break of DECISIONS 60 (one rule, shared
    with the demo bundle)."""
    from sixthfinger.export.demo_bundle import demo_subject as choose

    proto = load_protocol_config()
    return choose("eegnet_scratch", load_data_config(), list(proto.calibration.test_runs))[0]


def one_switch(rows: pd.DataFrame, gate_cls) -> pd.DataFrame:
    """Added after the pseudo-online results: the same decoders and gate on P(rest) against
    P(AH) + P(SF), replayed from the stored probabilities; any imagery period counts."""
    out = []
    for r in rows.itertuples():
        stem = replay_dir() / f"{r.subject}_{r.method}"
        tl = pd.read_parquet(f"{stem}_timeline.parquet")
        per = pd.read_parquet(f"{stem}_periods.parquet")
        runs = []
        for run, g in tl.groupby("run"):
            proba = po.any_imagery(g[["p_rest", "p_ah", "p_sf"]].to_numpy())
            ends = np.rint(g.t.to_numpy() * SFREQ).astype(int)
            acts = po.activations(po.replay(proba, gate_cls), ends)
            runs.append(po.RunReplay(per[per.run == run], acts, SFREQ))
        out.append(dict(subject=r.subject, method=r.method, flagged=r.flagged,
                        **po.switch_metrics(runs)))  # fmt: skip
    return pd.DataFrame(out)


def run_cuts(paths, subjects: list[str]) -> dict:
    """Each replayed run's length and its boundary cuts (samples), read from the run file."""
    listed = list_processed_runs(paths.processed)
    files = {(r.subject, r.session, int(r.run)): r.path for r in listed}
    out = {}
    for subject in subjects:
        periods = pd.read_parquet(replay_dir() / f"{subject}_ts_lr_periods.parquet")
        for run in sorted(periods.run.unique()):
            rec = read_eeglab_mat(files[(subject, "pre", int(run))])
            cuts = rec.event_samples[np.array(rec.event_codes) == "boundary"]
            out[(subject, int(run))] = (rec.data_uv.shape[1], cuts)
    return out


def stopped_early(per: pd.DataFrame, cuts: np.ndarray) -> pd.DataFrame:
    """Each period stopped at the next period's start and at its first cut (the code audit's
    check; protocol §6b scores the full 7 s and 6 s)."""
    per = per.sort_values("start").reset_index(drop=True)
    nxt = np.r_[per.start.to_numpy()[1:], np.iinfo(np.int64).max]
    stop = np.minimum(per.stop.to_numpy(), nxt)
    for i, start in enumerate(per.start.to_numpy()):
        inside = cuts[(cuts > start) & (cuts < stop[i])]
        if inside.size:
            stop[i] = inside.min()
    return per.assign(stop=stop)


def details(rows: pd.DataFrame, switch: pd.DataFrame, paths, n_window: int):
    """Per method and for the replay as a whole, from the stored timelines and periods."""
    subjects = sorted(rows.subject.unique())
    runs = run_cuts(paths, subjects)
    per_method = []
    for method in METHOD_ORDER:
        mine = rows[rows.method == method].set_index("subject")
        false = early = 0
        again = []
        for subject in subjects:
            stem = replay_dir() / f"{subject}_{method}"
            tl = pd.read_parquet(f"{stem}_timeline.parquet")
            per = pd.read_parquet(f"{stem}_periods.parquet")
            replays = []
            for run, g in tl.groupby("run"):
                ends = np.rint(g.t.to_numpy() * SFREQ).astype(int)
                acts = po.activations(g.active.to_numpy(), ends)
                onsets = acts["sample"].to_numpy()
                rest = per[(per.run == run) & (per.kind == "rest")]
                for start, stop in zip(rest.start, rest.stop, strict=True):
                    inside = onsets[(onsets >= start) & (onsets < stop)]
                    false += len(inside)
                    early += int((inside - start < EARLY_S * SFREQ).sum())
                kept = stopped_early(per[per.run == run][["kind", "start", "stop"]],
                                     runs[(subject, int(run))][1])  # fmt: skip
                replays.append(po.RunReplay(kept, acts, SFREQ))
            again.append(dict(subject=subject, **po.subject_metrics(replays)))
        again = pd.DataFrame(again).set_index("subject")
        switched = switch[switch.method == method]
        if false != int(mine.false_activations.sum()):
            raise SystemExit(f"{method}: the timelines no longer give the stored false activations")
        change = {f"{c}_stopped_early_change": float((again[c] - mine[c]).mean()) for c in RATES}
        moved = (again[RATES[:3]] - mine[RATES[:3]]).abs().max(axis=1) > 0
        per_method.append(dict(
            method=method, n=len(mine), n_sf_half=int((mine.sf_detection_rate >= 0.5).sum()),
            n_sf_none=int((mine.sf_detection_rate == 0).sum()),
            sf_detection_max=mine.sf_detection_rate.max(),
            ah_as_sf_over_sf_detection=mine.ah_as_sf_rate.mean() / mine.sf_detection_rate.mean(),
            false_activations=false, false_first_seconds=early, false_first_share=early / false,
            n_switch_half=int((switched.imagery_detection_rate >= 0.5).sum()),
            **change, n_detection_moved_stopped_early=int(moved.sum()),
        ))  # fmt: skip

    stride = round(po.STRIDE_S * SFREQ)
    kept, n_periods, overlapping, with_cut, spacing = [], 0, 0, 0, []
    for subject in subjects:
        per = pd.read_parquet(replay_dir() / f"{subject}_ts_lr_periods.parquet")
        for run, p in per.groupby("run"):
            n_times, cuts = runs[(subject, int(run))]
            every = po.window_ends(n_times, n_window, stride, np.array([]))
            kept.append(len(po.window_ends(n_times, n_window, stride, cuts)) / len(every))
            p = p.sort_values("start")
            start, stop = p.start.to_numpy(), p.stop.to_numpy()
            n_periods += len(p)
            overlapping += int((stop[:-1] > start[1:]).sum())
            with_cut += sum(
                bool(((cuts > a) & (cuts < b)).any()) for a, b in zip(start, stop, strict=True)
            )
            spacing += list(np.diff(p[p.kind == "rest"].start.to_numpy()) / SFREQ)
    silent = rows[rows.method == METHOD_ORDER[0]]
    silent_p = silent.n_rest_periods / (silent.n_rest_periods + silent.n_sf_periods)
    replay = {
        "windows kept per run (share)": {"runs": len(kept), "median": float(np.median(kept)),
                                         "min": float(min(kept)), "max": float(max(kept))},
        "periods": {"total": n_periods, "overlapping the next": overlapping,
                    "holding a boundary cut": with_cut},
        "rest onset to the next rest onset (s)": {
            "intervals": len(spacing), "min": float(np.min(spacing)),
            "p5": float(np.percentile(spacing, 5)), "median": float(np.median(spacing)),
            "p95": float(np.percentile(spacing, 95)), "max": float(np.max(spacing))},
        "a gate that never fires": {
            "P correct, mean over patients": float(silent_p.mean()),
            "ITR bits per minute, mean over patients":
                float(np.mean([po.itr_bits_per_minute(x) for x in silent_p]))},
        "early false activation": {"seconds": EARLY_S, "rest period seconds": po.REST_S,
                                   "share of the rest period": EARLY_S / po.REST_S},
        "patients reaching half of their SF periods with any method":
            int(rows[rows.sf_detection_rate >= 0.5].subject.nunique()),
    }  # fmt: skip
    return pd.DataFrame(per_method), replay


def summarise(figures: bool = True) -> None:
    paths = get_paths()
    rows = pd.concat([pd.read_parquet(f) for f in sorted(replay_dir().glob("*_metrics.parquet"))])
    rows = rows.sort_values(["method", "subject"]).reset_index(drop=True)
    summary = paths.results / "summary"
    rows.to_csv(summary / "rq4_pseudo_online.csv", index=False, float_format="%.6g")
    metrics = ["sf_detection_rate", "ah_detection_rate", "ah_as_sf_rate", "false_per_minute",
               "sf_latency_s", "itr_bits_per_min"]  # fmt: skip
    table = []
    groups = [((m, "all"), rows[rows.method == m]) for m in METHOD_ORDER]
    groups += [((m, "unflagged"), rows[(rows.method == m) & ~rows.flagged]) for m in METHOD_ORDER]
    for (method, population), g in groups:
        for metric in metrics:
            v = g[metric].dropna().to_numpy()
            mean, lo, hi = bootstrap_ci(v) if len(v) else (np.nan, np.nan, np.nan)
            table.append(dict(method=method, population=population, metric=metric, n=len(v),
                              mean=mean, ci_lo=lo, ci_hi=hi,
                              median=float(np.median(v)) if len(v) else np.nan))  # fmt: skip
    pd.DataFrame(table).to_csv(summary / "rq4_pseudo_online_table.csv", index=False,
                               float_format="%.6g")  # fmt: skip
    switch = one_switch(rows, po.load_gate_class())
    switch.to_csv(summary / "rq4_pseudo_online_switch.csv", index=False, float_format="%.6g")
    st = []
    for method, g in switch.groupby("method"):
        for metric in ("imagery_detection_rate", "false_per_minute", "latency_s"):
            mean, lo, hi = bootstrap_ci(g[metric].dropna().to_numpy())
            st.append(dict(method=method, metric=metric, n=int(g[metric].notna().sum()),
                           mean=mean, ci_lo=lo, ci_hi=hi))  # fmt: skip
    pd.DataFrame(st).to_csv(summary / "rq4_pseudo_online_switch_table.csv", index=False,
                            float_format="%.6g")  # fmt: skip
    print(pd.DataFrame(st).to_string(index=False))
    repro = reproduction(paths)
    repro.to_csv(summary / "rq4_pseudo_online_repro.csv", index=False, float_format="%.3g")
    print(repro.to_string(index=False))
    per_method, replay = details(rows, switch, paths, load_data_config().n_times)
    per_method.to_csv(summary / "rq4_pseudo_online_details.csv", index=False, float_format="%.6g")
    (summary / "rq4_pseudo_online_replay.json").write_text(json.dumps(replay, indent=2) + "\n")
    if figures:
        figure(rows, demo_subject(paths), paths.root / "docs" / "figures")


def figure(rows: pd.DataFrame, subject: str, figures) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from sixthfinger.viz.plots import save, use_style

    use_style()
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.6, 3.0), gridspec_kw={"width_ratios": [1, 1.6]})
    colours = dict(zip(METHOD_ORDER, ["#1f77b4", "#ff7f0e", "#2ca02c", "#9467bd"], strict=True))
    for method, g in rows.groupby("method"):
        a.scatter(g.false_per_minute, g.sf_detection_rate, s=12, color=colours[method],
                  label=method, alpha=0.8)  # fmt: skip
    a.set_xlabel("false activations per minute of rest")
    a.set_ylabel("SF imagery periods detected")
    a.legend(frameon=False, fontsize=6)
    stem = replay_dir() / f"{subject}_eegnet_scratch"
    tl, per = (
        pd.read_parquet(f"{stem}_timeline.parquet"),
        pd.read_parquet(f"{stem}_periods.parquet"),
    )
    run = tl.run.min()
    tl, per = tl[tl.run == run], per[per.run == run]
    t_end = tl.t.min() + 120  # two minutes
    shade = {"rest": "0.9", "AH": "#ffe0b3", "SF": "#d0e4f5"}
    for p in per[per.t0 < t_end].itertuples():
        b.axvspan(p.t0, p.t1, color=shade[p.kind], lw=0)
    w = tl[tl.t <= t_end].reset_index(drop=True)
    # Windows skipped at a boundary leave a gap: break the lines there.
    gap = np.r_[False, np.diff(w.t.to_numpy()) > po.STRIDE_S * 1.5]
    w.loc[gap, ["p_sf", "p_ah"]] = np.nan
    b.plot(w.t, w.p_sf, color="#1f77b4", lw=0.8, label="P(SF)")
    b.plot(w.t, w.p_ah, color="#ff7f0e", lw=0.8, label="P(AH)")
    for command, y, colour in ((po.AH, 1.12, "#ff7f0e"), (po.SF, 1.2, "#1f77b4")):
        on = np.where(w.active == command, y, np.nan)
        b.plot(w.t, on, color=colour, lw=3, solid_capstyle="butt",
               label=f"gate: {po.COMMANDS[command]}")  # fmt: skip
    from matplotlib.patches import Patch

    handles = b.get_legend_handles_labels()[0] + [
        Patch(color=c, label=f"{k} period") for k, c in shade.items()
    ]
    b.set_xlabel(f"time in run {run:02d} (s), {subject}, eegnet_scratch")
    b.set_ylim(0, 1.3)
    b.set_yticks([0, 0.5, 1])
    b.legend(handles=handles, frameon=False, fontsize=5.5, ncol=4, loc="upper center",
             bbox_to_anchor=(0.5, -0.22))  # fmt: skip
    save(fig, figures, "rq4_pseudo_online")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subjects", nargs="*")
    ap.add_argument("--summarise", action="store_true")
    ap.add_argument("--no-figures", action="store_true", help="with --summarise: tables only")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    if args.summarise:
        summarise(figures=not args.no_figures)
        return
    cfg = get_paths().configs / "experiments" / f"{EXPERIMENT}.yaml"
    run_experiment(cfg, subjects=args.subjects, on_fitted=make_hook(po.load_gate_class()))


if __name__ == "__main__":
    main()
