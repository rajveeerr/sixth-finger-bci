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
in every table (gate provenance, protocol §6b).
"""

from __future__ import annotations

import argparse
import logging

import numpy as np
import pandas as pd

from sixthfinger.config import load_data_config, load_protocol_config
from sixthfinger.data.epochs import run_signal
from sixthfinger.data.loading import list_processed_runs
from sixthfinger.evaluation import pseudo_online as po
from sixthfinger.evaluation.runner import load_experiment, run_experiment
from sixthfinger.evaluation.stats import bootstrap_ci
from sixthfinger.paths import current_git_sha, get_paths

log = logging.getLogger("pseudo_online")
EXPERIMENT = "rq4_pseudo_online"
FLAGGED = ("sub-01", "sub-03")
SFREQ = 250.0  # the processed runs' rate; run_signal refuses any other
METHOD_ORDER = ["csp_lda", "ts_lr", "rct_tslr", "eegnet_scratch"]


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


def summarise() -> None:
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
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    if args.summarise:
        summarise()
        return
    cfg = get_paths().configs / "experiments" / f"{EXPERIMENT}.yaml"
    run_experiment(cfg, subjects=args.subjects, on_fitted=make_hook(po.load_gate_class()))


if __name__ == "__main__":
    main()
