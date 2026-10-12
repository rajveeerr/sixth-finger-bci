"""Summarise the calibration study: curves, efficiency and the confirmatory tests (P08 4.7-4.8).

uv run python scripts/summarise_calibration.py

Reads results/runs/{rq2_calib_s1,rq3_calib_s2,rq2_rq3_post}/scores.parquet (those that exist)
and writes results/summary/calib_*.csv and the rq2_*/rq3_* figures in docs/figures/.

Pre-registration 3.4-3.5 and 5.1-5.3, protocol 6-7, deviation log 2026-10-11/12:
- per-subject value at a k = mean over the random draws (k = 0 and k = all: the one draw);
  the chronological draw only in the sensitivity rows;
- ALC over K = {1, 2, 3, 5, 10} (S1) or {1, 2, 3, 5} (S2), on the k where both methods of a
  pair are defined; chance 1/3 (T2), 1/2 (T3);
- confirmatory pair rct_tslr vs ts_lr: H2a, H2b, H3 (a T3, b T2; Holm across 2), H3c
  (vs ah_proxy at k = 2, 5; Holm across 2), on pre (n = 22), without sub-01/sub-03 (n = 20),
  with the chronological draw, and on post (n = 24, and n = 23 with sub-21/sub-22 averaged);
- secondary pair eegnet_ea_ft vs eegnet_scratch: H2a, H2b, H3 on pre, n = 22;
- descriptive: H2a per k (Holm across 5), k*, trials saved, minutes, Friedman/Nemenyi,
  SF recall, the S2 SF-vs-AH share.
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
from scipy.stats import studentized_range

from sixthfinger.config import load_data_config, load_protocol_config
from sixthfinger.evaluation.stats import alc, friedman, k_star, paired_alc, subject_curve
from sixthfinger.evaluation.summary import describe, holm_family, paired
from sixthfinger.paths import get_paths
from sixthfinger.viz.plots import save, use_style

log = logging.getLogger("calib")
EXPERIMENTS = ["rq2_calib_s1", "rq3_calib_s2", "rq2_rq3_post"]
S1, S2 = "S1_new_user", "S2_new_command"
T2, T3 = "T2_rest_ah_sf", "T3_sf_vs_rest"
PAIR = ("rct_tslr", "ts_lr")
SECONDARY = ("eegnet_ea_ft", "eegnet_scratch")
K_ALC = {S1: [1, 2, 3, 5, 10], S2: [1, 2, 3, 5]}
CHANCE = {T2: 1 / 3, T3: 1 / 2}
THRESHOLDS = {T2: [0.60, 0.70], T3: [0.70]}
TRIAL_S, REST_SET_MIN = 14.0, 40 * 7 / 60
ALPHA = 0.05


# Per-subject values ------------------------------------------------------------------------


def load(runs: Path) -> pd.DataFrame:
    frames = [
        pd.read_parquet(p) for e in EXPERIMENTS if (p := runs / e / "scores.parquet").exists()
    ]
    if not frames:
        raise SystemExit(f"no calibration scores under {runs}")
    scores = pd.concat(frames, ignore_index=True)
    scores["k"] = scores.k.astype(int)
    return scores


def subject_values(scores: pd.DataFrame, value: str = "bal_acc") -> pd.DataFrame:
    """One value per (scenario, task, session, method, subject, k), random draws averaged."""
    out = subject_curve(scores, value)
    chrono = scores[scores.draw.astype(str) == "chrono"]
    keys = ["scenario", "task", "session", "method", "subject", "k"]
    c = chrono.groupby(keys, as_index=False)[value].mean().rename(columns={value: "chrono"})
    out = out.merge(c, on=keys, how="left")
    # k = 0 and k = all have one draw, which is also the chronological one.
    one = out.chrono.isna() & out.k.isin([0, max(out.k)])
    out.loc[one, "chrono"] = out.loc[one, value]
    return out


def curve(values: pd.DataFrame, method: str, subject: str, scenario, task, session, col):
    g = values[
        (values.method == method) & (values.subject == subject) & (values.scenario == scenario)
        & (values.task == task) & (values.session == session)
    ].set_index("k")[col]  # fmt: skip
    if not g.index.is_unique:
        raise ValueError(f"{method} {subject} {scenario} {task}: one k from two experiments")
    return g


def populations(session: str, subjects: list[str], dev: list[str]) -> dict[str, list[str]]:
    if session == "pre":
        return {"all": subjects, "without_dev": [s for s in subjects if s not in dev]}
    return {"all": subjects, "linked_merged": subjects}


# Confirmatory tests -----------------------------------------------------------------------


def two_sided_category(p: float, median: float) -> str:
    if p < ALPHA and median > 0:
        return "supported"
    if p < ALPHA and median < 0:
        return "contrary"
    return "inconclusive"


def pair_alcs(values, pair, scenario, task, session, col):
    """Per-subject ALC of both methods over K, on the k where both are defined."""
    rows = []
    for subject in sorted(set(values.subject)):
        a = curve(values, pair[0], subject, scenario, task, session, col)
        b = curve(values, pair[1], subject, scenario, task, session, col)
        ks = [k for k in K_ALC[scenario] if k in a.index and k in b.index]
        if len(ks) < 2:
            continue
        alc_a, alc_b, used = paired_alc(
            np.array(ks), a[ks].to_numpy(), b[ks].to_numpy(), CHANCE[task]
        )
        rows.append(dict(subject=subject, a=alc_a, b=alc_b, k_used=",".join(map(str, used))))
    return pd.DataFrame(rows, columns=["subject", "a", "b", "k_used"])


def at_k(values, method, scenario, task, session, k, col) -> pd.Series:
    g = values[
        (values.method == method) & (values.scenario == scenario) & (values.task == task)
        & (values.session == session) & (values.k == k)
    ]  # fmt: skip
    return g.set_index("subject")[col]


def _finish(sub: pd.DataFrame, population: str, data_cfg) -> pd.DataFrame:
    """Restrict to the population; for linked_merged average sub-21 and sub-22."""
    if population == "linked_merged":
        merged = sub.assign(subject=sub.subject.map(data_cfg.split_group))
        return merged.groupby("subject", as_index=False)[["a", "b"]].mean()
    return sub


def confirmatory(values: pd.DataFrame, data_cfg, dev: list[str]) -> pd.DataFrame:
    rows = []
    for session in sorted(set(values.session)):
        subjects = sorted(set(values[values.session == session].subject))
        for population, members in populations(session, subjects, dev).items():
            for basis, col in (("random", "bal_acc"), ("chrono", "chrono")):
                if session != "pre" and basis == "chrono":
                    continue  # 5.2: the chronological draw is a pre-session sensitivity check
                if population == "without_dev" and basis == "chrono":
                    continue
                pairs = [("confirmatory", PAIR)]
                if session == "pre" and population == "all" and basis == "random":
                    pairs.append(("secondary", SECONDARY))
                run = set(values[values.session == session].method)
                pairs = [(role, pair) for role, pair in pairs if set(pair) <= run]
                for role, pair in pairs:
                    rows += _rows(
                        values, role, pair, session, population, members, basis, col, data_cfg
                    )
    return pd.DataFrame(rows)


def _test_row(hyp, role, pair, session, population, basis, sub, alternative, **extra) -> dict:
    wide = sub.set_index("subject")[["a", "b"]]
    res = paired(wide, "a", "b", alternative=alternative, scale=1.0)
    return dict(hypothesis=hyp, role=role, pair=f"{pair[0]} - {pair[1]}", session=session,
                population=population, draw_basis=basis, **res, **extra)  # fmt: skip


def _rows(values, role, pair, session, population, members, basis, col, data_cfg) -> list[dict]:
    out = []
    keep = lambda df: _finish(df[df.subject.isin(members)], population, data_cfg)  # noqa: E731
    # H2a: S1, T2, ALC over {1, 2, 3, 5, 10}, two-sided.
    if S1 in set(values.scenario):
        sub = keep(pair_alcs(values, pair, S1, T2, session, col))
        r = _test_row("H2a", role, pair, session, population, basis, sub, "two-sided",
                      scenario=S1, task=T2, quantity="ALC")  # fmt: skip
        r["category"] = two_sided_category(r["p"], r["median_diff"])
        out.append(r)
        # H2b: [BA(a) - BA(b)] at k = 5 minus the same at k = all, one-sided > 0.
        a5, b5 = (at_k(values, m, S1, T2, session, 5, col) for m in pair)
        a20, b20 = (at_k(values, m, S1, T2, session, 20, col) for m in pair)
        d = pd.DataFrame({"a": a5 - b5, "b": a20 - b20}).dropna().reset_index()
        d = keep(d.rename(columns={"index": "subject"}))
        r = _test_row("H2b", role, pair, session, population, basis, d, "greater",
                      scenario=S1, task=T2, quantity="advantage at k=5 minus at k=all")  # fmt: skip
        r["category"] = "supported" if r["p"] < ALPHA else "inconclusive"
        out.append(r)
    # H3: S2, ALC over {1, 2, 3, 5} of T3 (a) and of T2 (b), two-sided, Holm across 2.
    if S2 in set(values.scenario):
        h3 = []
        for outcome, task in (("H3a", T3), ("H3b", T2)):
            sub = keep(pair_alcs(values, pair, S2, task, session, col))
            h3.append(_test_row(outcome, role, pair, session, population, basis, sub, "two-sided",
                                scenario=S2, task=task, quantity="ALC"))  # fmt: skip
        adj = holm_family({r["hypothesis"]: r["p"] for r in h3})
        for r in h3:
            r["p_holm"] = adj[r["hypothesis"]]
            r["category"] = two_sided_category(r["p_holm"], r["median_diff"])
        cats = {r["category"] for r in h3}
        overall = (
            "mixed" if cats >= {"supported", "contrary"}
            else "supported" if "supported" in cats
            else "contrary" if "contrary" in cats
            else "inconclusive"
        )  # fmt: skip
        for r in h3:
            r["family_category"] = overall
        out += h3
        # H3c: S2, T3, rct_tslr vs ah_proxy at k = 2 and 5, one-sided, Holm across 2.
        if role == "confirmatory":
            h3c = []
            for k in (2, 5):
                a = at_k(values, pair[0], S2, T3, session, k, col)
                b = at_k(values, "ah_proxy", S2, T3, session, k, "bal_acc")
                d = keep(pd.DataFrame({"a": a, "b": b}).dropna().reset_index()
                         .rename(columns={"index": "subject"}))  # fmt: skip
                h3c.append(_test_row(f"H3c_k{k}", role, (pair[0], "ah_proxy"), session,
                                     population, basis, d, "greater", scenario=S2, task=T3,
                                     quantity=f"BA at k={k}"))  # fmt: skip
            adj = holm_family({r["hypothesis"]: r["p"] for r in h3c})
            n_sig = sum(adj[r["hypothesis"]] < ALPHA for r in h3c)
            for r in h3c:
                r["p_holm"] = adj[r["hypothesis"]]
                r["category"] = "supported" if r["p_holm"] < ALPHA else "inconclusive"
                r["family_category"] = (
                    "supported" if n_sig == 2 else "partial" if n_sig else "inconclusive"
                )
            out += h3c
    return out


def h2a_per_k(values: pd.DataFrame) -> pd.DataFrame:
    """Secondary: H2a's pair at each of its five k, two-sided, Holm across the 5."""
    rows = []
    for k in K_ALC[S1]:
        a, b = (at_k(values, m, S1, T2, "pre", k, "bal_acc") for m in PAIR)
        res = paired(pd.DataFrame({"a": a, "b": b}), "a", "b", scale=100.0)
        rows.append(dict(k=k, **res))
    out = pd.DataFrame(rows)
    adj = holm_family({str(r.k): r.p for r in out.itertuples()})
    out["p_holm"] = [adj[str(k)] for k in out.k]
    return out


# Descriptive summaries ---------------------------------------------------------------------


def minutes(scenario: str, k: int, transfer: bool) -> float:
    m = (2 * k if scenario == S1 else k) * TRIAL_S / 60
    return m + (REST_SET_MIN if k == 0 and transfer else 0.0)


TRANSFER = {"pooled_tslr", "rct_mdm", "rct_tslr", "eegnet_ea_ft"}


def curves(values: pd.DataFrame, dev: list[str]) -> pd.DataFrame:
    rows = []
    keys = ["scenario", "task", "session", "method", "k"]
    for key, g in values.groupby(keys):
        for population, members in populations(key[2], sorted(set(g.subject)), dev).items():
            if population == "linked_merged":
                continue
            v = g[g.subject.isin(members)]
            d = describe(v.bal_acc)
            rows.append(dict(zip(keys, key, strict=True), population=population, **d,
                             sf_recall=v.sf_recall.mean() if "sf_recall" in v else np.nan,
                             minutes=minutes(key[0], key[4], key[3] in TRANSFER)))  # fmt: skip
    return pd.DataFrame(rows)


def efficiency(values: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (scenario, task, session, method, subject), g in values.groupby(
        ["scenario", "task", "session", "method", "subject"]
    ):
        c = g.set_index("k").bal_acc.dropna()
        ks = [k for k in K_ALC[scenario] if k in c.index]
        row = dict(scenario=scenario, task=task, session=session, method=method, subject=subject,
                   alc=alc(np.array(ks), c[ks].to_numpy(), CHANCE[task]) if len(ks) > 1 else np.nan,
                   alc_k=",".join(map(str, ks)))  # fmt: skip
        grid = c.sort_index()
        for thr in THRESHOLDS[task]:
            ks_ = k_star(grid.index.to_numpy(), grid.to_numpy(), thr)
            row[f"k_star_{round(thr * 100)}"] = ks_ if np.isfinite(ks_) else np.nan
            row[f"censored_{round(thr * 100)}"] = not np.isfinite(ks_)
        rows.append(row)
    return pd.DataFrame(rows)


def trials_saved(eff: pd.DataFrame, pair, scenario, task, session, thr: int) -> dict:
    col, cen = f"k_star_{thr}", f"censored_{thr}"
    e = eff[(eff.scenario == scenario) & (eff.task == task) & (eff.session == session)]
    a, b = (e[e.method == m].set_index("subject") for m in pair)
    both = a.join(b, lsuffix="_a", rsuffix="_b", how="inner")
    reach = both[~both[f"{cen}_a"] & ~both[f"{cen}_b"]]
    saved = reach[f"{col}_b"] - reach[f"{col}_a"]
    return dict(pair=f"{pair[0]} - {pair[1]}", scenario=scenario, task=task, session=session,
                threshold=thr / 100, n_both_reach=len(reach),
                n_only_first=int((~both[f"{cen}_a"] & both[f"{cen}_b"]).sum()),
                n_only_second=int((both[f"{cen}_a"] & ~both[f"{cen}_b"]).sum()),
                n_neither=int((both[f"{cen}_a"] & both[f"{cen}_b"]).sum()),
                median_trials_saved=float(saved.median()) if len(saved) else np.nan,
                mean_trials_saved=float(saved.mean()) if len(saved) else np.nan)  # fmt: skip


def friedman_table(values: pd.DataFrame, ks: list[int]) -> pd.DataFrame:
    rows = []
    pre = values[values.session == "pre"]
    for (scenario, task), g in pre.groupby(["scenario", "task"]):
        for k in ks:
            wide = g[g.k == k].pivot_table(index="subject", columns="method", values="bal_acc")
            wide = wide.dropna(axis=1, how="any")  # only methods defined for every subject
            if wide.shape[1] < 3:
                continue
            res = friedman(wide)
            n, m = wide.shape
            cd = (
                studentized_range.ppf(1 - ALPHA, m, np.inf)
                / np.sqrt(2)
                * np.sqrt(m * (m + 1) / (6 * n))
            )
            for method, rank in res["mean_ranks"].items():
                rows.append(dict(scenario=scenario, task=task, k=k, n_subjects=n,
                                 n_methods=m, chi2=res["chi2"], p=res["p"], nemenyi_cd=cd,
                                 method=method, mean_rank=rank))  # fmt: skip
    return pd.DataFrame(rows)


def sf_vs_ah(scores: pd.DataFrame) -> pd.DataFrame:
    s = scores[
        (scores.scenario == S2) & (scores.task == T3) & scores.method.isin([*PAIR, "ah_proxy"])
    ]
    v = subject_curve(s.dropna(subset=["sf_vs_ah"]), "sf_vs_ah")
    return v.groupby(["session", "method", "k"], as_index=False).agg(
        mean_sf_vs_ah=("sf_vs_ah", "mean"), n=("sf_vs_ah", "size")
    )


def coverage(scores: pd.DataFrame) -> pd.DataFrame:
    return (
        scores.assign(defined=scores.bal_acc.notna(), reason=scores.reason.fillna(""))
        .groupby(["experiment", "scenario", "task", "method", "k", "reason"], as_index=False)
        .agg(rows=("subject", "size"), defined=("defined", "sum"), subjects=("subject", "nunique"))
    )


# P08 gate checks (deviation log 2026-10-11) --------------------------------------------------

NOSIGNAL_TOLERANCE = {T2: 0.08, T3: 0.10}


def sanity_vs_p06(values: pd.DataFrame, runs: Path) -> pd.DataFrame:
    """S1 at k = all, T2, trains on exactly P06's chrono T2 windows: the values must match."""
    path = runs / "rq1_context" / "scores.parquet"
    if not path.exists():
        return pd.DataFrame()
    p06 = pd.read_parquet(path)
    p06 = p06[(p06.protocol == "chrono") & (p06.task == T2) & (p06.session == "pre")
              & (p06.feature == "bandpower")]  # fmt: skip
    ref = p06.groupby(["method", "subject"]).bal_acc.mean().rename("p06")
    at_all = values[(values.scenario == S1) & (values.task == T2) & (values.session == "pre")
                    & (values.k == max(values.k))]  # fmt: skip
    ours = at_all.set_index(["method", "subject"]).bal_acc
    both = pd.concat([ours.rename("p08"), ref], axis=1, join="inner").reset_index()
    both["abs_diff"] = (both.p08 - both.p06).abs()
    return both.assign(within_0_005=both.abs_diff <= 0.005)


def zero_shot_check(values: pd.DataFrame, summary: Path) -> pd.DataFrame:
    """S1 k = 0 of eegnet_ea_ft against P07's zero-shot (the same rule, the same models)."""
    path = summary / "dl_zeroshot_subject_values.csv"
    if not path.exists():
        return pd.DataFrame()
    p07 = pd.read_csv(path).set_index(["task", "subject"]).bal_acc.rename("p07")
    ours = values[(values.method == "eegnet_ea_ft") & (values.scenario == S1)
                  & (values.session == "pre") & (values.k == 0)]  # fmt: skip
    both = pd.concat([ours.set_index(["task", "subject"]).bal_acc.rename("p08"), p07],
                     axis=1, join="inner").reset_index()  # fmt: skip
    return both.assign(abs_diff=(both.p08 - both.p07).abs())


def nosignal(runs: Path) -> pd.DataFrame:
    path = runs / "rq2_nosignal" / "scores.parquet"
    if not path.exists():
        return pd.DataFrame()
    s = pd.read_parquet(path)
    g = s.groupby(["task", "method"], as_index=False).agg(
        mean_bal_acc=("bal_acc", "mean"), n=("bal_acc", "count")
    )
    g["chance"] = g.task.map(CHANCE)
    g["tolerance"] = g.task.map(NOSIGNAL_TOLERANCE)
    return g.assign(passes=(g.mean_bal_acc - g.chance).abs() <= g.tolerance)


# Figures -------------------------------------------------------------------------------------

COLOURS = {"ts_lr": "#1f77b4", "rct_tslr": "#d62728", "csp_lda": "#9467bd", "mdm": "#8c564b",
           "pooled_tslr": "#7f7f7f", "rct_mdm": "#ff7f0e", "eegnet_scratch": "#17becf",
           "eegnet_ea_ft": "#2ca02c", "ah_proxy": "#000000"}  # fmt: skip


def figure_curves(cur: pd.DataFrame, figures: Path) -> None:
    pre = cur[(cur.session == "pre") & (cur.population == "all")]
    panels = [(S1, T2), (S1, T3), (S2, T3), (S2, T2)]
    fig, axes = plt.subplots(2, 2, figsize=(7.4, 6.6))
    handles = {}
    for ax, (scenario, task) in zip(axes.flat, panels, strict=True):
        g = pre[(pre.scenario == scenario) & (pre.task == task)]
        for method, m in g.groupby("method"):
            m = m.sort_values("k")
            x = np.log1p(m.k)
            colour = COLOURS.get(method, "0.5")
            (line,) = ax.plot(x, m["mean"], marker="o", ms=3, color=colour,
                              lw=1.6 if method in PAIR else 0.9, label=method)  # fmt: skip
            ax.fill_between(x, m.ci_lo, m.ci_hi, color=colour, alpha=0.12, lw=0)
            handles[method] = line
        ax.axhline(CHANCE[task], color="0.5", lw=0.8)
        for thr in THRESHOLDS[task]:
            ax.axhline(thr, color="0.7", lw=0.6, ls=":")
        ks = sorted(set(g.k))
        ax.set_xticks(np.log1p(ks), [str(k) if k < 20 else "all" for k in ks])
        name = task.split("_", 1)[1].replace("_", " ")
        ax.set_title(f"{scenario.split('_')[0]}: {name}", fontsize=8, pad=16)
        top = ax.secondary_xaxis("top")
        top.set_xticks(np.log1p(ks), [f"{minutes(scenario, k, False):.1f}" for k in ks])
        top.tick_params(labelsize=6)
        ax.set_xlabel("k (trials per class)" if scenario == S1 else "k (SF trials)", fontsize=8)
    for ax in axes[:, 0]:
        ax.set_ylabel("balanced accuracy")
    fig.legend(handles.values(), handles.keys(), loc="lower center", ncol=5, frameon=False,
               fontsize=7)  # fmt: skip
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    save(fig, figures, "rq2_calibration_curves")


def figure_sf_recall(cur: pd.DataFrame, figures: Path) -> None:
    g = cur[(cur.session == "pre") & (cur.population == "all") & (cur.scenario == S2)
            & cur.method.isin([*PAIR, "ah_proxy"])]  # fmt: skip
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.8), sharey=True)
    for ax, task in zip(axes, (T3, T2), strict=True):
        for method, m in g[g.task == task].groupby("method"):
            m = m.sort_values("k")
            ax.plot(np.log1p(m.k), m.sf_recall, marker="o", ms=3, color=COLOURS.get(method),
                    label=method)  # fmt: skip
        ks = sorted(set(g.k))
        ax.set_xticks(np.log1p(ks), [str(k) if k < 20 else "all" for k in ks])
        ax.set_title(f"S2 {task.split('_', 1)[1].replace('_', ' ')}: SF recall", fontsize=8)
        ax.set_xlabel("SF trials")
    axes[0].set_ylabel("SF recall")
    axes[0].legend(frameon=False, fontsize=7)
    save(fig, figures, "rq3_sf_recall_curves")


def figure_trials_saved(eff: pd.DataFrame, figures: Path) -> None:
    e = eff[(eff.scenario == S1) & (eff.task == T2) & (eff.session == "pre")]
    a, b = (e[e.method == m].set_index("subject") for m in PAIR)
    both = a.join(b, lsuffix="_rct", rsuffix="_ts", how="inner")
    never = 30  # drawn past "all" (20) for patients who never reach 60 %
    pts = pd.DataFrame(
        {"ts": both.k_star_60_ts.fillna(never), "rct": both.k_star_60_rct.fillna(never)}
    )
    counts = pts.value_counts().rename("n").reset_index()
    fig, ax = plt.subplots(figsize=(3.6, 3.6))
    ax.scatter(counts.ts, counts.rct, s=25 * counts.n, color="0.25", alpha=0.8)
    for r in counts.itertuples():
        if r.n > 1:
            ax.annotate(
                str(r.n), (r.ts, r.rct), xytext=(6, 4), textcoords="offset points", fontsize=7
            )
    ax.plot([0, never], [0, never], color="0.6", lw=0.8)
    ticks = [0, 5, 10, 20, never]
    labels = ["0", "5", "10", "all", "never"]
    ax.set_xticks(ticks, labels)
    ax.set_yticks(ticks, labels)
    ax.set_xlabel("k* for 60 %, ts_lr (trials per class)")
    ax.set_ylabel("k* for 60 %, rct_tslr")
    ax.set_title("S1, three-class, pre (marker size = patients)", fontsize=8)
    save(fig, figures, "rq2_trials_saved")


def figure_cd(fr: pd.DataFrame, figures: Path, scenario=S1, task=T2, k=5) -> None:
    g = fr[(fr.scenario == scenario) & (fr.task == task) & (fr.k == k)].sort_values("mean_rank")
    if g.empty:
        return
    fig, ax = plt.subplots(figsize=(6.0, 1.8))
    ax.scatter(g.mean_rank, np.zeros(len(g)), color="k", s=10)
    for i, r in enumerate(g.itertuples()):
        ax.annotate(r.method, (r.mean_rank, 0), xytext=(0, 8 + 10 * (i % 3)),
                    textcoords="offset points", ha="center", fontsize=7)  # fmt: skip
    cd = g.nemenyi_cd.iloc[0]
    ax.plot([g.mean_rank.min(), g.mean_rank.min() + cd], [-0.5, -0.5], color="k", lw=2)
    ax.text(g.mean_rank.min(), -0.9, f"CD = {cd:.2f}", fontsize=7)
    ax.set_yticks([])
    ax.set_ylim(-1.2, 1.5)
    ax.set_xlabel(f"mean rank ({scenario.split('_')[0]}, {task.split('_')[0]}, k = {k}; 1 = best)")
    save(fig, figures, "rq2_cd_k5")


def figure_heatmap(values: pd.DataFrame, figures: Path) -> None:
    v = values[(values.scenario == S1) & (values.task == T2) & (values.session == "pre")]
    wide = v[v.method.isin(PAIR)].pivot_table(index=["subject", "k"], columns="method",
                                              values="bal_acc")  # fmt: skip
    diff = (
        (wide[PAIR[0]] - wide[PAIR[1]])
        .rename("d")
        .reset_index()
        .pivot_table(index="subject", columns="k", values="d")
    )
    fig, ax = plt.subplots(figsize=(4.4, 5.0))
    lim = np.nanmax(np.abs(diff.to_numpy()))
    im = ax.imshow(diff.to_numpy(), cmap="RdBu_r", vmin=-lim, vmax=lim, aspect="auto")
    ax.set_xticks(range(diff.shape[1]), [str(k) if k < 20 else "all" for k in diff.columns])
    ax.set_yticks(range(diff.shape[0]), diff.index, fontsize=6)
    ax.set_xlabel("trials per class")
    fig.colorbar(im, ax=ax, label="rct_tslr - ts_lr (balanced accuracy)")
    save(fig, figures, "rq2_subject_heatmap")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("fontTools").setLevel(logging.WARNING)
    use_style()
    paths, data_cfg, proto = get_paths(), load_data_config(), load_protocol_config()
    summary, figures = paths.results / "summary", paths.root / "docs" / "figures"
    scores = load(paths.runs)
    values = subject_values(scores)
    sf = subject_curve(scores, "sf_recall")
    keys = ["scenario", "task", "session", "method", "subject", "k"]
    values = values.merge(sf[[*keys, "sf_recall"]], on=keys, how="left")
    values.to_csv(summary / "calib_subject_values.csv", index=False, float_format="%.6g")
    coverage(scores).to_csv(summary / "calib_coverage.csv", index=False)
    conf = confirmatory(values, data_cfg, list(proto.dev_subjects))
    conf.to_csv(summary / "calib_confirmatory.csv", index=False, float_format="%.6g")
    if {S1} <= set(values.scenario):
        h2a_per_k(values).to_csv(summary / "calib_h2a_per_k.csv", index=False, float_format="%.6g")
    cur = curves(values, list(proto.dev_subjects))
    cur.to_csv(summary / "calib_curves.csv", index=False, float_format="%.6g")
    eff = efficiency(values)
    eff.to_csv(summary / "calib_efficiency.csv", index=False, float_format="%.6g")
    saved = [
        trials_saved(eff, pair, sc, t, ses, thr)
        for pair in (PAIR, SECONDARY) for sc in (S1, S2) for t in (T2, T3)
        for ses in sorted(set(eff.session)) for thr in [round(x * 100) for x in THRESHOLDS[t]]
        if {pair[0], pair[1]} <= set(eff[(eff.scenario == sc) & (eff.session == ses)].method)
    ]  # fmt: skip
    pd.DataFrame(saved).to_csv(summary / "calib_trials_saved.csv", index=False, float_format="%.6g")
    fr = friedman_table(values, list(proto.stats.friedman_k))
    fr.to_csv(summary / "calib_friedman.csv", index=False, float_format="%.6g")
    if S2 in set(scores.scenario):
        sf_vs_ah(scores).to_csv(summary / "rq3_sf_vs_ah.csv", index=False, float_format="%.6g")
    for name, table in (
        ("calib_sanity_vs_p06", sanity_vs_p06(values, paths.runs)),
        ("calib_zeroshot_check", zero_shot_check(values, summary)),
        ("calib_nosignal", nosignal(paths.runs)),
    ):
        if len(table):
            table.to_csv(summary / f"{name}.csv", index=False, float_format="%.6g")
    figure_curves(cur, figures)
    if S2 in set(cur.scenario):
        figure_sf_recall(cur, figures)
    figure_trials_saved(eff, figures)
    figure_cd(fr, figures)
    figure_heatmap(values, figures)
    log.info("calibration summaries in %s", summary)


if __name__ == "__main__":
    main()
