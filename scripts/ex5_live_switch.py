"""Exploratory, added after the results: the central-channel switch played as if live.

The replay of question 4 (scripts/pseudo_online.py, protocol §6b) with the trial-level switch
of ex4_sf_command: `ts_lr` on the 14 central channels, learned on runs 01-02 for rest against
movement (M14) or rest against the sixth finger (S14), through the unchanged command gate, and
M14 with each patient's on-threshold chosen on runs 01-02 (M14_sure).

One part at a time, in this order:

uv run python scripts/ex5_live_switch.py --part repro    # rq4's ts_lr replayed again: must match
uv run python scripts/ex5_live_switch.py --part inner    # M14: learn run 01, replay run 02...
uv run python scripts/ex5_live_switch.py --part select   # ...and back; each patient's threshold
uv run python scripts/ex5_live_switch.py --part test     # learn runs 01-02, replay runs 03-04
uv run python scripts/ex5_live_switch.py --part summary

Settings: configs/experiments/ex5_live_switch.yaml, fixed before any replay of runs 03-04 is
scored. `select` writes the thresholds into the settings and refuses once an arm's replay of
runs 03-04 exists, unless the settings already hold them, which it then only checks. `test`
refuses without them and without a passing reproduction. Window-level probabilities go to
results/runs/ex5_live_switch/ and `summary` rebuilds every table from them without refitting.
Writes results/summary/ex5_live_switch_*. A few minutes on the Mac in all.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from functools import cache, lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

import sixthfinger.models  # noqa: F401  (registers every method)
from sixthfinger.config import load_data_config, load_protocol_config
from sixthfinger.data.channels import CENTRAL_14
from sixthfinger.data.epochs import load_windows, run_signal
from sixthfinger.data.loading import list_processed_runs
from sixthfinger.evaluation import exploratory as ex
from sixthfinger.evaluation import pseudo_online as po
from sixthfinger.evaluation.calibration import draw_calibration_set
from sixthfinger.evaluation.metrics import score
from sixthfinger.evaluation.runner import method_params, task_windows
from sixthfinger.evaluation.stats import bootstrap_ci, paired_test
from sixthfinger.models.registry import Batch, make_method
from sixthfinger.paths import current_git_sha, get_paths

NAME = "ex5_live_switch"
SETTINGS = get_paths().configs / "experiments" / f"{NAME}.yaml"
CONFIG = ex.settings(NAME)
RUNS_DIR = get_paths().runs / NAME
RQ4_REPLAY = get_paths().runs / "rq4_pseudo_online" / "replay"
REST, AH, SF = 0, 1, 2
SFREQ = 250.0  # the processed runs' rate; run_signal refuses any other
ARMS = ["M14", "S14", "M14_sure"]
BASELINES = ["eegnet_scratch", "ts_lr", "csp_lda"]
METRICS = ["imagery_detection_rate", "false_per_minute", "latency_s", "ah_on_rate", "sf_on_rate"]
RATES = {"imagery_detection_rate", "ah_on_rate", "sf_on_rate"}
# The switch is meant to turn on for either movement, so more catches of each kind is better.
HIGHER_IS_BETTER = {"imagery_detection_rate": True, "false_per_minute": False,
                    "latency_s": False, "ah_on_rate": True, "sf_on_rate": True}  # fmt: skip
# Which probability column turns each arm on; the three-class baselines add AH and SF.
ON_COLUMN = {"M14": "p_move", "S14": "p_sf", "M14_sure": "p_move"}
WINDOW_COLUMNS = ["subject", "arm", "fold", "run", "end", "p_rest", "p_ah", "p_sf", "p_move"]

log = logging.getLogger(NAME)


def out(name: str) -> Path:
    return get_paths().summary / f"{NAME}_{name}"


def windows_path(part: str) -> Path:
    return RUNS_DIR / f"windows_{part}.parquet"


def periods_path(part: str) -> Path:
    return RUNS_DIR / f"periods_{part}.parquet"


def setup_logging() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S")
    for h in (logging.StreamHandler(), logging.FileHandler(RUNS_DIR / "run.log")):
        h.setFormatter(fmt)
        log.addHandler(h)
    log.setLevel(logging.INFO)


def pre_subjects() -> list[str]:
    return ex.pre_subjects(load_data_config())


def central() -> list[int]:
    names = CONFIG["channels"]["central_14"]
    if tuple(names) != CENTRAL_14:
        raise SystemExit("the settings' central channels differ from CENTRAL_14")
    return ex.channel_index(load_data_config(), CENTRAL_14)


def patient(subject: str) -> tuple[np.ndarray, pd.DataFrame]:
    """Every cached pre window of one patient (REST, AH, SF), X: (n, 40, 1000) volts."""
    X, md = load_windows(get_paths().epochs, load_data_config(), subjects=[subject],
                         sessions=["pre"])  # fmt: skip
    return X, md.reset_index(drop=True)


@cache
def run_files() -> dict:
    return {(r.subject, r.session, int(r.run)): r.path
            for r in list_processed_runs(get_paths().processed)}  # fmt: skip


# Both arms replay the same two runs of a patient: read each once.
@lru_cache(maxsize=2)
def continuous(subject: str, run: int):
    """One run as the replay reads it: (40, samples) volts and its record, or None if excluded."""
    cfg = load_data_config()
    path = run_files().get((subject, CONFIG["session"], run))
    if path is None or cfg.is_run_excluded(subject, CONFIG["session"], f"{run:02d}"):
        return None
    data, rec = run_signal(path, cfg)
    if rec.sfreq != SFREQ:
        raise ValueError(f"{path.name}: sfreq {rec.sfreq}")
    return data, rec


def ts_lr(X: np.ndarray, y: np.ndarray, md: pd.DataFrame):
    params = method_params("ts_lr", get_paths().configs)
    m = make_method("ts_lr", n_classes=len(np.unique(y)), **params)
    return m.fit(Batch(X, y, md))


def arm_rows(arm: str, md: pd.DataFrame, runs) -> tuple[np.ndarray, np.ndarray]:
    """Training rows of an arm's model and their labels (M14: REST 0, AH and SF 1)."""
    in_runs = md.run.isin(runs)
    if arm == "M14":
        idx = md.index[in_runs].to_numpy()
        return idx, (md.label.to_numpy()[idx] != REST).astype(int)
    if arm == "S14":
        idx = md.index[in_runs & md.label.isin([REST, SF])].to_numpy()
        return idx, md.label.to_numpy()[idx]
    raise ValueError(arm)


def fit_arm(arm: str, X: np.ndarray, md: pd.DataFrame, runs):
    idx, y = arm_rows(arm, md, runs)
    ch = central()
    m = ts_lr(X[idx][:, ch], y, md.iloc[idx])
    expected = [REST, 1] if arm == "M14" else [REST, SF]
    if list(m.pipe[-1].classes_) != expected:
        raise AssertionError(f"{arm}: class order {m.pipe[-1].classes_}")
    return m


def as_columns(arm: str, proba: np.ndarray) -> dict:
    nan = np.full(len(proba), np.nan)
    if arm == "rq4_ts_lr":
        return dict(p_rest=proba[:, REST], p_ah=proba[:, AH], p_sf=proba[:, SF], p_move=nan)
    if arm == "M14":
        return dict(p_rest=proba[:, 0], p_ah=nan, p_sf=nan, p_move=proba[:, 1])
    return dict(p_rest=proba[:, 0], p_ah=nan, p_sf=proba[:, 1], p_move=nan)


def replay_rows(
    subject: str, arm: str, fold: str, run: int, model, chans
) -> tuple[list, pd.DataFrame]:
    """The model's probabilities for every replayed window of one run, and the run's periods."""
    got = continuous(subject, run)
    if got is None:
        return [], pd.DataFrame()
    data, rec = got
    signal = data if chans is None else data[chans]
    n_window = load_data_config().n_times
    ends, proba = po.window_proba(model.predict_proba, signal, rec.event_codes,
                                  rec.event_samples, rec.sfreq, n_window)  # fmt: skip
    rows = pd.DataFrame(dict(subject=subject, arm=arm, fold=fold, run=run, end=ends,
                             **as_columns(arm, proba)))  # fmt: skip
    per = po.periods(list(rec.event_codes), rec.event_samples, rec.sfreq, data.shape[1])
    return [rows], per.assign(subject=subject, run=run)


def save(frames: list[pd.DataFrame], periods: list[pd.DataFrame], part: str) -> None:
    sha = current_git_sha()
    w = pd.concat(frames, ignore_index=True)[WINDOW_COLUMNS].assign(git_sha=sha)
    p = pd.concat(periods, ignore_index=True).drop_duplicates(["subject", "run", "kind", "start"])
    w.to_parquet(windows_path(part), index=False)
    p.to_parquet(periods_path(part), index=False)
    log.info("wrote %s (%d windows) at %s", windows_path(part).name, len(w), sha)


def gate_runs(win: pd.DataFrame, per: pd.DataFrame, on: str, gate) -> list[po.RunReplay]:
    """One arm's stored windows of one patient through the gate, run by run."""
    runs = []
    for run, g in win.sort_values(["run", "end"]).groupby("run"):
        if on == "any_imagery":
            proba = po.any_imagery(g[["p_rest", "p_ah", "p_sf"]].to_numpy())
        else:
            proba = g[["p_rest", on]].to_numpy()
        acts = po.activations(po.replay(proba, gate), g.end.to_numpy())
        runs.append(po.RunReplay(per[per.run == run], acts, SFREQ))
    return runs


def switch(runs: list[po.RunReplay]) -> dict:
    return po.switch_metrics(runs) | po.switch_by_kind(runs)


# Reproduction ---------------------------------------------------------------------------------


def rq4_training(md: pd.DataFrame) -> np.ndarray:
    """The rows the rq4 runner fitted ts_lr on: S1, three classes, k = all, runs 01-02."""
    proto = load_protocol_config()
    k_all = max(proto.calibration.k_grid)
    pool = md[md.run.isin(CONFIG["train_runs"])]
    cd = draw_calibration_set(pool, [], [AH, SF], k_all, "0", k_all=k_all)
    return task_windows(pool.iloc[cd.labelled_idx], [REST, AH, SF]).index.to_numpy()


def committed_switch() -> pd.DataFrame:
    return pd.read_csv(get_paths().summary / "rq4_pseudo_online_switch.csv")


def at6(v: float) -> float:
    return float(f"{v:.6g}") if pd.notna(v) else np.nan


def same(a: pd.Series, b: pd.Series) -> tuple[bool, float]:
    """Equal cell by cell, NaN matching NaN; and the largest difference."""
    nan_a, nan_b = a.isna().to_numpy(), b.isna().to_numpy()
    d = (a.astype(float) - b.astype(float)).abs().to_numpy()
    worst = float(np.nanmax(d)) if (~nan_a & ~nan_b).any() else 0.0
    return bool((nan_a == nan_b).all() and worst == 0.0), worst


def part_repro() -> None:
    frames, periods = [], []
    test_runs = po.replayed_runs(CONFIG["replay_runs"], CONFIG["train_runs"])
    for subject in pre_subjects():
        X, md = patient(subject)
        idx = rq4_training(md)
        m = ts_lr(X[idx], md.label.to_numpy()[idx], md.iloc[idx])
        for run in test_runs:
            rows, per = replay_rows(subject, "rq4_ts_lr", "final", run, m, None)
            frames += rows
            periods.append(per)
        log.info("repro %s: %d training windows", subject, len(idx))
        del X
    save(frames, periods, "repro")
    repro_summary()


def repro_summary() -> None:
    win, per = pd.read_parquet(windows_path("repro")), pd.read_parquet(periods_path("repro"))
    gate = po.load_gate_class()
    ours = []
    for subject, g in win.groupby("subject"):
        runs = gate_runs(g, per[per.subject == subject], "any_imagery", gate)
        ours.append(dict(subject=subject, **po.switch_metrics(runs)))
    ours = pd.DataFrame(ours).set_index("subject")
    com = committed_switch()
    com = com[com.method == "ts_lr"].set_index("subject")
    rows = []
    for metric in ("n_imagery_periods", "imagery_detection_rate", "false_per_minute", "latency_s"):
        ok, worst = same(ours[metric].map(at6), com[metric].reindex(ours.index))
        rows.append(dict(check=f"ts_lr {metric} vs rq4_pseudo_online_switch.csv", n=len(ours),
                         identical=ok, max_abs_diff=worst))  # fmt: skip
    # The probabilities themselves, against the replay files the committed rows were made from.
    worst, n_win, ends_ok = 0.0, 0, True
    for subject, g in win.groupby("subject"):
        tl = pd.read_parquet(RQ4_REPLAY / f"{subject}_ts_lr_timeline.parquet")
        g = g.sort_values(["run", "end"])
        tl = tl.sort_values(["run", "t"])
        ends_ok &= np.array_equal(np.rint(tl.t.to_numpy() * SFREQ).astype(int), g.end.to_numpy())
        if len(tl) == len(g):
            d = np.abs(
                g[["p_rest", "p_ah", "p_sf"]].to_numpy() - tl[["p_rest", "p_ah", "p_sf"]].to_numpy()
            )
            worst = max(worst, float(d.max()))
        n_win += len(g)
    rows.append(dict(check="window ends equal the stored rq4 ts_lr timelines", n=n_win,
                     identical=bool(ends_ok), max_abs_diff=np.nan))  # fmt: skip
    name = "ts_lr probabilities vs the stored rq4 ts_lr timelines (not required to be exact)"
    rows.append(dict(check=name, n=n_win, identical=worst == 0.0, max_abs_diff=worst))
    table = pd.DataFrame(rows).assign(git_sha=current_git_sha())
    table.to_csv(out("repro.csv"), index=False, float_format="%.6g")
    log.info("\n%s", table.to_string(index=False))
    if not repro_passed():
        raise SystemExit("the reproduction of rq4's ts_lr failed: no arm may be replayed")


def repro_passed() -> bool:
    if not out("repro.csv").exists():
        return False
    t = pd.read_csv(out("repro.csv"))
    required = t[~t.check.str.contains("not required")]
    return bool(len(required) == 5 and required.identical.all())


# Inner replay and each patient's threshold ---------------------------------------------------


def part_inner() -> None:
    frames, periods = [], []
    folds = CONFIG["threshold_rule"]["inner_replay"]["folds"]
    for subject in pre_subjects():
        X, md = patient(subject)
        for fold, (learn, replay) in folds.items():
            if set(learn) & set(replay) or set(replay) - set(CONFIG["train_runs"]):
                raise ValueError(f"inner fold {fold} must replay another calibration run")
            m = fit_arm("M14", X, md, learn)
            for run in replay:
                rows, per = replay_rows(subject, "M14", fold, run, m, central())
                frames += rows
                periods.append(per)
        log.info("inner %s done", subject)
        del X
    save(frames, periods, "inner")


def candidates() -> np.ndarray:
    return np.round(np.arange(50, 100) / 100, 2)


def inner_curve() -> pd.DataFrame:
    win, per = pd.read_parquet(windows_path("inner")), pd.read_parquet(periods_path("inner"))
    if win.run.isin(CONFIG["replay_runs"]).any() or per.run.isin(CONFIG["replay_runs"]).any():
        raise AssertionError("the inner replay read a replayed test run")
    gate = po.load_gate_class()
    rows = []
    for subject, g in win.groupby("subject"):
        p = per[per.subject == subject]
        for t in candidates():
            m = switch(gate_runs(g, p, "p_move", po.with_threshold(gate, float(t))))
            rows.append(dict(subject=subject, threshold=float(t), **m))
    return pd.DataFrame(rows)


def part_select() -> None:
    recorded = CONFIG.get("threshold_choice")
    if recorded is None and windows_path("test").exists():
        raise SystemExit(
            "runs 03-04 already replayed for the arms: thresholds can no longer be chosen"
        )
    curve = inner_curve()
    limit = CONFIG["threshold_rule"]["limit_per_minute"]
    picked = []
    for subject, g in curve.groupby("subject"):
        p = po.lowest_quiet_threshold(g.threshold, g.false_per_minute, limit)
        at = g[g.threshold == p["threshold"]].iloc[0]
        usual = g[np.isclose(g.threshold, 0.6)].iloc[0]  # the gate's own threshold, for context
        picked.append(dict(subject=subject, threshold=p["threshold"],
                           inner_false_per_minute=p["false_per_minute"],
                           within_limit=p["within_limit"],
                           inner_detection_rate=at.imagery_detection_rate,
                           inner_false_per_minute_at_060=usual.false_per_minute,
                           inner_detection_rate_at_060=usual.imagery_detection_rate))  # fmt: skip
    picked = pd.DataFrame(picked)
    curve.to_csv(out("inner_curve.csv"), index=False, float_format="%.6g")
    picked.to_csv(out("thresholds.csv"), index=False, float_format="%.6g")
    log.info("\n%s", picked.to_string(index=False))
    chosen = {r.subject: float(r.threshold) for r in picked.itertuples()}
    if recorded is not None:
        # The thresholds were fixed before any arm's test replay; a re-run may only confirm them.
        if recorded["thresholds"] != chosen:
            raise SystemExit(f"recomputed thresholds {chosen} differ from the recorded ones")
        log.info("thresholds as recorded on %s", recorded["chosen_at"])
        return
    choice = {
        "thresholds": chosen,
        "n_within_limit": int(picked.within_limit.sum()),
        "chosen_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "files": f"{NAME}_thresholds.csv, {NAME}_inner_curve.csv (runs 01-02 only)",
    }
    import yaml

    with SETTINGS.open("a") as f:
        f.write(yaml.safe_dump({"threshold_choice": choice}, sort_keys=False, width=96))
    log.info("thresholds appended to %s", SETTINGS.name)


# Runs 03-04 ------------------------------------------------------------------------------------


def part_test() -> None:
    if CONFIG.get("threshold_choice") is None or not out("thresholds.csv").exists():
        raise SystemExit("no thresholds in the settings yet: run --part select first")
    if not repro_passed():
        raise SystemExit("the reproduction of rq4's ts_lr has not passed: run --part repro first")
    if windows_path("test").exists():
        log.info("%s exists; nothing to do", windows_path("test").name)
        return
    test_runs = po.replayed_runs(CONFIG["replay_runs"], CONFIG["train_runs"])
    frames, periods, trials = [], [], []
    ch = central()
    for subject in pre_subjects():
        X, md = patient(subject)
        held = md.index[md.run.isin(test_runs)].to_numpy()
        for arm in ("M14", "S14"):
            m = fit_arm(arm, X, md, CONFIG["train_runs"])
            for run in test_runs:
                rows, per = replay_rows(subject, arm, "final", run, m, ch)
                frames += rows
                periods.append(per)
            proba = m.predict_proba(X[held][:, ch])
            trials.append(pd.DataFrame(dict(subject=subject, arm=arm,
                                            trial_uid=md.trial_uid.to_numpy()[held],
                                            run=md.run.to_numpy()[held],
                                            label=md.label.to_numpy()[held],
                                            p_rest=proba[:, 0], p_on=proba[:, 1])))  # fmt: skip
        log.info("test %s done", subject)
        del X
    pd.concat(trials, ignore_index=True).assign(git_sha=current_git_sha()).to_parquet(
        RUNS_DIR / "trials_test.parquet", index=False
    )
    save(frames, periods, "test")


# Summary -------------------------------------------------------------------------------------


def arm_values() -> pd.DataFrame:
    win, per = pd.read_parquet(windows_path("test")), pd.read_parquet(periods_path("test"))
    thresholds = CONFIG["threshold_choice"]["thresholds"]
    gate = po.load_gate_class()
    rows = []
    for (subject, arm), g in win.groupby(["subject", "arm"]):
        p = per[per.subject == subject]
        rows.append(dict(subject=subject, arm=arm, threshold=gate.threshold,
                         **switch(gate_runs(g, p, ON_COLUMN[arm], gate))))  # fmt: skip
        if arm == "M14":
            t = thresholds[subject]
            sure = po.with_threshold(gate, t)
            rows.append(dict(subject=subject, arm="M14_sure", threshold=t,
                             **switch(gate_runs(g, p, "p_move", sure))))  # fmt: skip
    return pd.DataFrame(rows)


def baseline_values() -> tuple[pd.DataFrame, dict]:
    """The committed rows, with hand and finger periods apart from the stored rq4 timelines."""
    com = committed_switch()
    com = com[com.method.isin(BASELINES)]
    gate = po.load_gate_class()
    rows, worst, ok = [], 0.0, True
    for r in com.itertuples():
        stem = RQ4_REPLAY / f"{r.subject}_{r.method}"
        tl = pd.read_parquet(f"{stem}_timeline.parquet")
        per = pd.read_parquet(f"{stem}_periods.parquet")
        win = tl.assign(end=np.rint(tl.t.to_numpy() * SFREQ).astype(int))
        m = switch(gate_runs(win, per, "any_imagery", gate))
        for metric in ("n_imagery_periods", "imagery_detection_rate", "false_per_minute",
                       "latency_s"):  # fmt: skip
            a, b = at6(m[metric]), getattr(r, metric)
            if pd.isna(a) and pd.isna(b):
                continue
            ok &= a == b
            worst = max(worst, abs(a - b) if pd.notna(a) and pd.notna(b) else np.inf)
        rows.append(dict(subject=r.subject, arm=r.method, threshold=gate.threshold,
                         n_imagery_periods=r.n_imagery_periods,
                         imagery_detection_rate=r.imagery_detection_rate,
                         false_per_minute=r.false_per_minute, latency_s=r.latency_s,
                         n_ah_periods=m["n_ah_periods"], ah_on_rate=m["ah_on_rate"],
                         n_sf_periods=m["n_sf_periods"], sf_on_rate=m["sf_on_rate"]))  # fmt: skip
    check = {
        "stored rq4 timelines give the committed switch rows (eegnet_scratch, ts_lr, csp_lda)": [
            bool(ok),
            float(worst),
        ],
        "stored rq4 timelines commit": sorted(
            {str(pd.read_parquet(f).git_sha.iloc[0]) for f in RQ4_REPLAY.glob("*_metrics.parquet")}
        ),
    }
    return pd.DataFrame(rows), check


def trial_fires() -> pd.DataFrame:
    """Share of the cached windows of runs 03-04 each model reads as on, per class and patient."""
    t = pd.read_parquet(RUNS_DIR / "trials_test.parquet")
    t["on"] = t.p_on > t.p_rest  # a tie reads as rest, as argmax does
    out_ = t.pivot_table(index=["subject", "arm"], columns="label", values="on", aggfunc="mean")
    out_.columns = [f"trial_fire_{n}" for n in ("rest", "ah", "sf")]
    return out_.reset_index()


def ex4_check(trials: pd.DataFrame) -> dict:
    """S14 must be ex4's headline switch: its balanced accuracy and fire rates per patient."""
    t = pd.read_parquet(RUNS_DIR / "trials_test.parquet")
    t = t[(t.arm == "S14") & t.label.isin([REST, SF])]
    bal = {s: score(g.label.to_numpy(), g[["p_rest", "p_on"]].to_numpy(), [REST, SF])["bal_acc"]
           for s, g in t.groupby("subject")}  # fmt: skip
    pp = pd.read_csv(get_paths().summary / "ex4_sf_command_per_patient.csv").set_index("subject")
    s14 = trials[trials.arm == "S14"].set_index("subject")
    at4 = lambda v: float(f"{v:.4g}")  # noqa: E731  (the per-patient file keeps 4 digits)
    pairs = {
        "balanced accuracy, REST and SF windows": (pd.Series(bal), pp.test_ts_lr_c14),
        "fires on AH windows": (s14.trial_fire_ah, pp.fire_ah_ts_lr_c14),
        "fires on REST windows": (s14.trial_fire_rest, pp.fire_rest_ts_lr_c14),
        "fires on SF windows": (s14.trial_fire_sf, pp.fire_sf_ts_lr_c14),
    }
    res = {}
    for name, (ours, theirs) in pairs.items():
        ok, worst = same(ours.map(at4), theirs.reindex(ours.index))
        res[f"S14 vs ex4_sf_command ts_lr_c14, {name} (22 patients, 4 digits as stored)"] = [
            ok,
            worst,
        ]
    return res


def describe(arm: str, population: str, metric: str, v: pd.Series) -> dict:
    v = v.dropna()
    mean, lo, hi = bootstrap_ci(v.to_numpy()) if len(v) else (np.nan, np.nan, np.nan)
    return dict(arm=arm, population=population, metric=metric, n=len(v), mean=mean, ci_lo=lo,
                ci_hi=hi, median=float(np.median(v)) if len(v) else np.nan)  # fmt: skip


def paired(arm: str, base: str, metric: str, a: pd.Series, b: pd.Series) -> dict:
    """One paired comparison over the patients both have, and again without sub-01 and sub-03."""
    both = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    scale = 100 if metric in RATES else 1
    res = paired_test(both.a.to_numpy(), both.b.to_numpy())
    d = both.a - both.b
    sign = 1 if HIGHER_IS_BETTER[metric] else -1
    no_dev = d.drop(list(ex.DEV_SUBJECTS), errors="ignore")
    m, lo, hi = bootstrap_ci(no_dev.to_numpy())
    return dict(
        comparison=f"{arm} vs {base}", metric=metric, arm=arm, baseline=base, n=res["n"],
        n_left_out=int(len(a) - len(both)), arm_mean=both.a.mean(), base_mean=both.b.mean(),
        diff=res["mean_diff"] * scale, diff_ci_lo=res["ci_lo"] * scale,
        diff_ci_hi=res["ci_hi"] * scale,
        diff_unit="points" if metric in RATES else ("per minute" if metric == "false_per_minute"
                                                     else "s"),
        p_wilcoxon=res["p"], better=int((sign * d > 0).sum()), worse=int((sign * d < 0).sum()),
        tied=int((d == 0).sum()), n_without_dev=len(no_dev), diff_without_dev=m * scale,
        diff_ci_lo_without_dev=lo * scale, diff_ci_hi_without_dev=hi * scale,
    )  # fmt: skip


def page_choice(table: pd.DataFrame) -> dict:
    """The page rule of the settings, applied to the means over the 22 patients."""
    t = table[table.population == "all"].set_index(["arm", "metric"])["mean"]
    base_det = t[("eegnet_scratch", "imagery_detection_rate")]
    base_false = t[("eegnet_scratch", "false_per_minute")]
    beats = {
        arm: bool(t[(arm, "imagery_detection_rate")] > base_det
                  and t[(arm, "false_per_minute")] < base_false)
        for arm in ("M14", "M14_sure")
    }  # fmt: skip
    winners = [a for a, b in beats.items() if b]
    winners.sort(key=lambda a: (t[(a, "false_per_minute")], -t[(a, "imagery_detection_rate")]))
    return {
        "beats_eegnet_scratch": beats,
        "page_shows": winners[0] if winners else "eegnet_scratch",
    }


def part_summary() -> None:
    if CONFIG.get("threshold_choice") is None:
        raise SystemExit("no thresholds recorded")
    picked = pd.read_csv(out("thresholds.csv"))
    if {r.subject: float(r.threshold) for r in picked.itertuples()} != CONFIG["threshold_choice"][
        "thresholds"
    ]:
        raise SystemExit("the thresholds file differs from the recorded thresholds")
    arms = arm_values()
    base, check_base = baseline_values()
    trials = trial_fires()
    values = pd.concat([arms, base], ignore_index=True)
    values = values.merge(trials, on=["subject", "arm"], how="left")
    sure = trials[trials.arm == "M14"].assign(arm="M14_sure")
    values = values.set_index(["subject", "arm"])
    values.update(sure.set_index(["subject", "arm"]))  # the same model as M14
    values = values.reset_index()
    values["flagged"] = values.subject.isin(ex.DEV_SUBJECTS)
    order = {a: i for i, a in enumerate(ARMS + BASELINES)}
    values = values.sort_values(["arm", "subject"], key=lambda s: s.map(order) if s.name == "arm"
                                else s).reset_index(drop=True)  # fmt: skip
    values["git_sha"] = current_git_sha()
    values.to_csv(out("values.csv"), index=False, float_format="%.6g")

    table = []
    for arm in ARMS + BASELINES:
        g = values[values.arm == arm].set_index("subject")
        for population, rows in (("all", g), ("without_dev", g.drop(list(ex.DEV_SUBJECTS)))):
            for metric in METRICS:
                table.append(describe(arm, population, metric, rows[metric]))
            if arm in ("M14", "S14", "M14_sure"):
                for col in ("trial_fire_rest", "trial_fire_ah", "trial_fire_sf"):
                    table.append(describe(arm, population, col, rows[col]))
            if arm == "M14_sure":
                table.append(describe(arm, population, "threshold", rows["threshold"]))
    table = pd.DataFrame(table)
    table.to_csv(out("table.csv"), index=False, float_format="%.6g")

    wide = {a: values[values.arm == a].set_index("subject") for a in ARMS + BASELINES}
    pairs = [(a, b) for a in ARMS for b in ("eegnet_scratch", "ts_lr")] + [("M14_sure", "M14")]
    rows = [paired(a, b, m, wide[a][m], wide[b][m]) for a, b in pairs for m in METRICS]
    paired_table = pd.DataFrame(rows)
    paired_table.to_csv(out("paired.csv"), index=False, float_format="%.6g")

    thr = picked.threshold
    checks = {
        f"reproduction of rq4's ts_lr ({NAME}_repro.csv) passed": repro_passed(),
        **check_base,
        **ex4_check(trials),
        "patients": int(values.subject.nunique()),
        "imagery, hand and sixth-finger periods per patient (min, max)": [
            [int(values[c].min()), int(values[c].max())]
            for c in ("n_imagery_periods", "n_ah_periods", "n_sf_periods")
        ],
        "replayed windows of runs 03-04 per arm": {
            a: int(n)
            for a, n in pd.read_parquet(windows_path("test")).groupby("arm").size().items()
        },
        "M14_sure thresholds within the limit on runs 01-02": int(picked.within_limit.sum()),
        "M14_sure thresholds (min, median, max)": [float(f(thr)) for f in (min, np.median, max)],
        "M14_sure thresholds below / at / above the gate's 0.6": [
            int((thr < 0.6 - 1e-9).sum()),
            int(np.isclose(thr, 0.6).sum()),
            int((thr > 0.6 + 1e-9).sum()),
        ],
        "page rule (settings page_rule)": page_choice(table),
        "git sha at summary": current_git_sha(),
    }
    out("checks.json").write_text(json.dumps(checks, indent=2) + "\n")
    for k, v in checks.items():
        log.info("check: %s = %s", k, v)
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        t = table[(table.population == "all") & table.metric.isin(METRICS)]
        means = t.pivot_table(index="arm", columns="metric", values="mean", aggfunc="first")
        log.info("\n%s", means.round(4))
        cols = ["comparison", "metric", "n", "arm_mean", "base_mean", "diff", "diff_ci_lo",
                "diff_ci_hi", "p_wilcoxon", "better", "worse", "diff_without_dev"]  # fmt: skip
        log.info("\n%s", paired_table[cols].round(4).to_string(index=False))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parts = ["repro", "inner", "select", "test", "summary"]
    ap.add_argument("--part", required=True, choices=parts)
    args = ap.parse_args()
    setup_logging()
    gate = po.load_gate_class()()
    fixed = CONFIG["gate"]
    if (gate.alpha, gate.threshold, gate.dwell, gate.release) != (
        fixed["alpha"], fixed["threshold"], fixed["dwell"], fixed["release"]
    ):  # fmt: skip
        raise SystemExit("the server's gate differs from the settings")
    t0, c0 = time.perf_counter(), time.process_time()
    log.info("part %s start, git %s", args.part, current_git_sha())
    {
        "repro": part_repro,
        "inner": part_inner,
        "select": part_select,
        "test": part_test,
        "summary": part_summary,
    }[args.part]()
    log.info("part %s done: %.0f s wall, %.0f s CPU (this process)", args.part,
             time.perf_counter() - t0, time.process_time() - c0)  # fmt: skip


if __name__ == "__main__":
    main()
