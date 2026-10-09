"""Summaries, the H1 test and the figures of RQ1 from the scores of the RQ1 runs.

uv run python scripts/summarise_rq1.py

Reads results/runs/rq1_benchmark (and rq1_context when present); writes
results/summary/rq1_{subject_values,table,stats,replica_check,runtime}.csv and
docs/figures/rq1_{leakage_paired,methods}.{pdf,png}.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from sixthfinger.config import load_data_config, load_protocol_config
from sixthfinger.evaluation.summary import (
    WITHIN_PROTOCOLS,
    describe,
    holm_family,
    merge_linked,
    one_sided_category,
    paired,
    subject_values,
)
from sixthfinger.paths import get_paths

log = logging.getLogger("rq1")

UNIT = ["experiment", "task", "method", "feature", "protocol", "subject", "session"]
H1_METHOD, H1_FEATURE, H1_TASK = "csp_lda", "bandpower", "T1_ah_vs_sf"
SESSIONS = ["pre", "post", "follow"]
METHOD_ORDER = ["csp_lda", "csp_lda_replica", "csp_svm", "fbcsp_lda", "mdm", "ts_lr"]
# Wang et al. (2026), Scientific Data 13, 1109, "Classification accuracy": mean accuracy (%)
# of CSP+LDA and CSP+SVM, AH vs SF, per group and session (the paper's leaky protocol).
PUBLISHED = {
    ("B", "pre"): (85.09, 85.63),
    ("B", "post"): (85.59, 85.57),
    ("B", "follow"): (85.78, 86.42),
    ("T", "pre"): (86.02, 85.26),
    ("T", "post"): (85.95, 85.59),
    ("T", "follow"): (83.60, 83.42),
}
DESCRIPTIVE = [
    ("paper_replica", "cv_leakfree", "greater"),
    ("cv_leakfree", "loro", "two-sided"),
    ("loro", "chrono", "two-sided"),
]


def load_scores(runs: Path) -> pd.DataFrame:
    frames = []
    for name in ("rq1_benchmark", "rq1_context"):
        path = runs / name / "scores.parquet"
        if path.exists():
            frames.append(pd.read_parquet(path))
        else:
            log.warning("%s not found", path)
    if not frames:
        raise SystemExit(f"No RQ1 scores under {runs}")
    scores = pd.concat(frames, ignore_index=True)
    if scores.bal_acc.isna().any():
        bad = scores[scores.bal_acc.isna()]
        log.warning("%d fold rows without a score: %s", len(bad), bad.reason.unique())
    return scores


def per_subject(scores: pd.DataFrame, n_classes: dict[str, int]) -> pd.DataFrame:
    parts = [subject_values(rows, UNIT, n_classes[task]) for task, rows in scores.groupby("task")]
    return pd.concat(parts, ignore_index=True)


def populations(values: pd.DataFrame, session: str, data_cfg, dev: list[str]):
    """The subject sets a session is reported on (pre-registration 3.1 and 5.2)."""
    if session == "pre":
        yield "all", values
        yield "without_dev", values[~values.subject.isin(dev)]
    elif session == "post":
        yield "all", values
        slim = values[["protocol", "subject", "bal_acc", "acc"]]
        yield "linked_merged", merge_linked(slim, data_cfg.split_group)
    else:
        yield "all", values


def group_table(sv: pd.DataFrame, data_cfg, dev: list[str]) -> pd.DataFrame:
    rows = []
    for (task, method, feature, protocol, session), vals in sv.groupby(
        ["task", "method", "feature", "protocol", "session"]
    ):
        for population, v in populations(vals, session, data_cfg, dev):
            above = vals[vals.subject.isin(v.subject)].above_chance if population == "all" else None
            rows.append(
                dict(
                    task=task,
                    method=method,
                    feature=feature,
                    protocol=protocol,
                    session=session,
                    population=population,
                    **describe(v.bal_acc),
                    mean_acc=float(v.acc.mean()),
                    n_above_chance=int(above.sum()) if above is not None else np.nan,
                )
            )
    table = pd.DataFrame(rows)
    table["protocol"] = pd.Categorical(table.protocol, WITHIN_PROTOCOLS, ordered=True)
    table["session"] = pd.Categorical(table.session, SESSIONS, ordered=True)
    return table.sort_values(["task", "session", "method", "feature", "protocol", "population"])


def _wide(vals: pd.DataFrame) -> pd.DataFrame:
    return vals.pivot_table(index="subject", columns="protocol", values="bal_acc")


def stats_table(sv: pd.DataFrame, data_cfg, dev: list[str]) -> pd.DataFrame:
    t1 = sv[sv.task == H1_TASK]
    rows = []
    h1 = t1[(t1.method == H1_METHOD) & (t1.feature == H1_FEATURE)]
    pre_category = None
    for session in SESSIONS:
        for population, vals in populations(h1[h1.session == session], session, data_cfg, dev):
            res = paired(_wide(vals), "paper_replica", "cv_leakfree", "greater")
            category = one_sided_category(res["p"])
            if session == "pre" and population == "all":
                test_id, role, pre_category = "H1", "confirmatory", category
            elif session == "pre":
                test_id, role = "H1_without_dev", "sensitivity"
            elif session == "post":
                test_id, role = f"H1_post_{population}", "replication"
            else:
                test_id, role = "H1_follow", "descriptive"
            rows.append(
                dict(
                    test_id=test_id,
                    role=role,
                    task=H1_TASK,
                    method=H1_METHOD,
                    feature=H1_FEATURE,
                    session=session,
                    population=population,
                    comparison="paper_replica - cv_leakfree",
                    **res,
                    p_holm=res["p"],
                    category=category,
                )
            )
    for row in rows:
        row["same_category_as_pre"] = row["category"] == pre_category
    # Descriptive tests: one Holm family per session over every method and comparison.
    for session in SESSIONS:
        family = []
        for (method, feature), vals in t1[t1.session == session].groupby(["method", "feature"]):
            wide = _wide(vals)
            for a, b, alternative in DESCRIPTIVE:
                family.append(
                    dict(
                        test_id="descriptive",
                        role="descriptive",
                        task=H1_TASK,
                        method=method,
                        feature=feature,
                        session=session,
                        population="all",
                        comparison=f"{a} - {b}",
                        **paired(wide, a, b, alternative),
                    )
                )
        adj = holm_family({i: r["p"] for i, r in enumerate(family)})
        for i, r in enumerate(family):
            r["p_holm"] = adj[i]
        rows += family
    return pd.DataFrame(rows)


def replica_check(sv: pd.DataFrame, data_cfg) -> pd.DataFrame:
    """Our replicas next to the published accuracy, per group and session."""
    bci = set(data_cfg.subjects.bci_group)
    rep = sv[(sv.task == H1_TASK) & (sv.protocol == "paper_replica")]
    rep = rep.assign(group=np.where(rep.subject.isin(bci), "B", "T"))
    rows = []
    for (method, feature, session), vals in rep.groupby(["method", "feature", "session"]):
        for group in ("B", "T", "all"):
            v = vals if group == "all" else vals[vals.group == group]
            pub = PUBLISHED.get((group, session), (np.nan, np.nan))
            rows.append(
                dict(
                    method=method,
                    feature=feature,
                    session=session,
                    group=group,
                    n=len(v),
                    mean_acc_pct=100 * v.acc.mean(),
                    mean_bal_acc_pct=100 * v.bal_acc.mean(),
                    published_csp_lda_acc_pct=pub[0],
                    published_csp_svm_acc_pct=pub[1],
                )
            )
    return pd.DataFrame(rows)


def runtime_table(scores: pd.DataFrame) -> pd.DataFrame:
    """Fit time per fold; the replica's pre-fit and FBCSP's filter bank run once per session
    and are not in these numbers."""
    return scores.groupby(["experiment", "method", "protocol"], as_index=False).agg(
        n_fits=("fit_seconds", "size"),
        total_fit_seconds=("fit_seconds", "sum"),
        mean_fit_seconds=("fit_seconds", "mean"),
        git_sha=("git_sha", lambda s: ",".join(sorted(set(s)))),
    )


def figures(sv: pd.DataFrame, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from sixthfinger.viz.plots import ACCENT, protocol_lines, reference_line, save, use_style

    use_style()
    pre = sv[(sv.session == "pre") & (sv.task == H1_TASK)]
    panels = [
        ("CSP+LDA, 5-35 Hz (H1)", "csp_lda", "bandpower"),
        ("Replica, mu ERSP", "csp_lda_replica", "ersp_mu"),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(6.2, 3.0), sharey=True)
    for ax, (title, method, feature) in zip(axes, panels, strict=True):
        wide = _wide(pre[(pre.method == method) & (pre.feature == feature)])
        ci = pd.DataFrame([describe(wide[p]) for p in WITHIN_PROTOCOLS], index=WITHIN_PROTOCOLS)
        ax.axhspan(0.85, 0.86, color="#f2c94c", alpha=0.35, lw=0, zorder=0)
        ax.annotate(
            "published 85-86 %",
            (0.02, 0.862),
            xycoords=("axes fraction", "data"),
            fontsize=7,
            color="#6f6f6f",
            va="bottom",
        )
        protocol_lines(ax, wide, WITHIN_PROTOCOLS, title, chance=0.5, ci=ci)
    axes[0].set_ylabel("Balanced accuracy, AH vs SF (pre)")
    axes[0].set_ylim(0.2, 1.02)
    save(fig, out, "rq1_leakage_paired")

    loro = sv[(sv.session == "pre") & (sv.protocol == "loro") & (sv.feature == "bandpower")]
    tasks = [
        ("T1_ah_vs_sf", "AH vs SF", 0.5),
        ("T2_rest_ah_sf", "REST vs AH vs SF", 1 / 3),
        ("T3_sf_vs_rest", "SF vs REST", 0.5),
    ]
    methods = [m for m in METHOD_ORDER if m in set(loro.method)]
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.8), sharey=True)
    rng = np.random.default_rng(0)  # horizontal jitter of the dots only
    for ax, (task, title, chance) in zip(axes, tasks, strict=True):
        rows = loro[loro.task == task]
        data = [rows[rows.method == m].bal_acc.to_numpy() for m in methods]
        if not any(len(d) for d in data):
            ax.set_title(f"{title} (not run)")
            continue
        ax.boxplot(
            data,
            widths=0.5,
            showfliers=False,
            medianprops={"color": ACCENT, "lw": 1.5},
            boxprops={"color": "#8a8a8a"},
            whiskerprops={"color": "#8a8a8a"},
            capprops={"color": "#8a8a8a"},
        )
        for i, d in enumerate(data, start=1):
            ax.scatter(i + rng.uniform(-0.15, 0.15, len(d)), d, s=8, color="#4d4d4d", zorder=3)
        reference_line(ax, chance, "chance")
        ax.set_xticks(range(1, len(methods) + 1), methods, rotation=35, ha="right")
        ax.set_title(f"{title} (n = {rows.subject.nunique()})")
        ax.grid(axis="y", color="#e6e6e6", lw=0.6)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("Balanced accuracy, leave-run-out (pre)")
    save(fig, out, "rq1_methods")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-figures", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    logging.getLogger("fontTools").setLevel(logging.WARNING)
    paths, data_cfg, proto = get_paths(), load_data_config(), load_protocol_config()
    scores = load_scores(paths.runs)
    n_classes = {task: len(names) for task, names in proto.tasks.items()}
    sv = per_subject(scores, n_classes)
    out = paths.summary
    out.mkdir(parents=True, exist_ok=True)
    sv.sort_values(UNIT).to_csv(out / "rq1_subject_values.csv", index=False, float_format="%.6g")
    table = group_table(sv, data_cfg, proto.dev_subjects)
    table.to_csv(out / "rq1_table.csv", index=False, float_format="%.6g")
    stats = stats_table(sv, data_cfg, proto.dev_subjects)
    stats.to_csv(out / "rq1_stats.csv", index=False, float_format="%.6g")
    replica_check(sv, data_cfg).to_csv(
        out / "rq1_replica_check.csv", index=False, float_format="%.6g"
    )
    runtime_table(scores).to_csv(out / "rq1_runtime.csv", index=False, float_format="%.6g")
    h1 = stats[stats.test_id == "H1"].iloc[0]
    log.info(
        "H1: n=%d, inflation %.2f points [%.2f, %.2f], W=%s, p=%.3g -> %s",
        h1.n,
        h1.mean_diff,
        h1.ci_lo,
        h1.ci_hi,
        h1.W,
        h1.p,
        h1.category,
    )
    if not args.no_figures:
        figures(sv, paths.figures)


if __name__ == "__main__":
    main()
