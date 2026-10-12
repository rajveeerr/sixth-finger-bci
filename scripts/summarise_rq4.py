"""P09 Study 1: does hemisphere mirroring help transfer? (lean finish: classical methods only)

uv run python scripts/merge_scores.py results/kaggle/rq4-mirror-*/results/runs
uv run python scripts/summarise_rq4.py

Per patient, method and k: the mean over the random draws of `rq4_mirror` (mirrored) minus
that of P08's `rq2_calib_s1` (unmirrored), the same units; both ran on Kaggle CPUs. Paired
two-sided Wilcoxon per (method, k), Holm over the k of each method; also by affected side
(mirroring changes the data of the 9 left-hemiplegic patients only; the others gain or lose
through their sources). Exploratory. Writes results/summary/rq4_mirror.csv (per patient),
rq4_mirror_table.csv and docs/figures/rq4_mirror_effect.
"""

from __future__ import annotations

import pandas as pd

from sixthfinger.data.channels import hemiplegia_side
from sixthfinger.evaluation.runner import part_files
from sixthfinger.evaluation.stats import paired_test
from sixthfinger.evaluation.summary import holm_family
from sixthfinger.paths import get_paths

METHODS = ["pooled_tslr", "rct_tslr"]
K = [0, 2, 5, 10]


def subject_means(path, mirrored: bool) -> pd.DataFrame:
    if part_files(path):
        raise SystemExit(f"{path.parent}: part files of a stopped run; resume it first")
    s = pd.read_parquet(path)
    s = s[(s.scenario == "S1_new_user") & (s.task == "T2_rest_ah_sf") & (s.session == "pre")
          & s.method.isin(METHODS) & (s.draw != "chrono")]  # fmt: skip
    s = s.assign(k=s.k.astype(int))
    s = s[s.k.isin(K)]
    return (s.groupby(["method", "subject", "k"], as_index=False).bal_acc.mean()
            .assign(mirrored=mirrored))  # fmt: skip


def main() -> None:
    paths = get_paths()
    runs = paths.runs
    both = pd.concat([subject_means(runs / "rq4_mirror" / "scores.parquet", True),
                      subject_means(runs / "rq2_calib_s1" / "scores.parquet", False)])  # fmt: skip
    w = both.pivot_table(index=["method", "subject", "k"], columns="mirrored", values="bal_acc")
    w = w.dropna().rename(columns={True: "mirrored", False: "unmirrored"}).reset_index()
    w["diff"] = w.mirrored - w.unmirrored
    w["side"] = w.subject.map(hemiplegia_side)
    summary = paths.results / "summary"
    w.to_csv(summary / "rq4_mirror.csv", index=False, float_format="%.6g")
    rows = []
    for method in METHODS:
        tests = {}
        for k in K:
            g = w[(w.method == method) & (w.k == k)]
            res = paired_test(g.mirrored.to_numpy(), g.unmirrored.to_numpy())
            tests[str(k)] = res["p"]
            by_side = {f"mean_diff_{s}": g[g.side == s]["diff"].mean() for s in ("L", "R")}
            rows.append(dict(method=method, k=k, n=res["n"], n_left=int((g.side == "L").sum()),
                             mean_mirrored=g.mirrored.mean(), mean_unmirrored=g.unmirrored.mean(),
                             mean_diff=res["mean_diff"], ci_lo=res["ci_lo"], ci_hi=res["ci_hi"],
                             p=res["p"], **by_side))  # fmt: skip
        adj = holm_family(tests)
        for r in rows:
            if r["method"] == method:
                r["p_holm"] = adj[str(r["k"])]
    table = pd.DataFrame(rows)
    table.to_csv(summary / "rq4_mirror_table.csv", index=False, float_format="%.6g")
    print(table.to_string(index=False))
    figure(table, paths.figures)


def figure(table: pd.DataFrame, figures) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from sixthfinger.viz.plots import save, use_style

    use_style()
    fig, ax = plt.subplots(figsize=(3.6, 2.8))
    for method, colour in zip(METHODS, ["#9467bd", "#2ca02c"], strict=True):
        g = table[table.method == method]
        ax.errorbar(g.k, 100 * g.mean_diff, yerr=[100 * (g.mean_diff - g.ci_lo),
                    100 * (g.ci_hi - g.mean_diff)], color=colour, marker="o", ms=3, capsize=2,
                    label=method)  # fmt: skip
        ax.plot(g.k, 100 * g.mean_diff_L, color=colour, ls=":", lw=1, marker="v", ms=3)
    ax.axhline(0, color="0.6", lw=0.8)
    ax.set_xticks(K)
    ax.set_xlabel("trials per class")
    ax.set_ylabel("mirrored minus unmirrored (points)")
    ax.set_title("S1 three-class, pre; dotted: left-hemiplegic patients", fontsize=7)
    ax.legend(frameon=False, fontsize=6)
    save(fig, figures, "rq4_mirror_effect")


if __name__ == "__main__":
    main()
