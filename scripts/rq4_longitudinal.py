"""P09 Study 2 (lean finish, DECISIONS 59): does a decoder calibrated before training still
work after it, and how many new trials bring it back?

uv run python scripts/rq4_longitudinal.py

Per patient with `pre` and a later session (`post`, then `follow`), on the three-class task,
tested on runs 03-04 of the later session:
- pre_unchanged: `ts_lr` on every `pre` window of the task (all four runs), never re-trained;
- new_only: `ts_lr` on k trials per class drawn from runs 01-02 of the later session;
- pooled: `ts_lr` on the `pre` windows plus those k trials;
- recentred: as `rct_tslr`, with the patient's own `pre` session as its only source: `pre`
  re-centred by its own mean, the later session by its unlabelled set (its rest windows of
  runs 01-02 at k = 0, the drawn windows at k > 0, as in P08), then tangent space and
  logistic regression with the chosen target weight.
k in {0, 5, 10} trials per class, drawn among complete trials with P08's seeds (10 draws).
Exploratory. Writes results/summary/rq4_longitudinal.csv (per patient, mean over draws),
rq4_longitudinal_table.csv and docs/figures/rq4_longitudinal.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from pyriemann.estimation import Covariances
from pyriemann.tangentspace import TangentSpace
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline

from sixthfinger.config import load_data_config, load_protocol_config
from sixthfinger.data.epochs import load_windows
from sixthfinger.evaluation.calibration import draw_calibration_set
from sixthfinger.evaluation.metrics import score
from sixthfinger.evaluation.runner import method_params, task_windows
from sixthfinger.evaluation.stats import bootstrap_ci
from sixthfinger.models.registry import Batch, make_method
from sixthfinger.paths import current_git_sha, get_paths
from sixthfinger.preprocessing.covariance import centring_filters, recentre

log = logging.getLogger("rq4_longitudinal")
CLASSES = [0, 1, 2]
K_GRID = [0, 5, 10]
LATER = ["post", "follow"]
ARMS = ["pre_unchanged", "new_only", "pooled", "recentred"]


def fit_ts_lr(X, rows: pd.DataFrame):
    m = make_method("ts_lr", n_classes=3, **method_params("ts_lr", get_paths().configs))
    return m.fit(Batch(X[rows.index], rows.label.to_numpy(), rows))


class Recentred:
    """`rct_tslr` with one source domain, the patient's own `pre` session."""

    def __init__(self, params: dict):
        self.p = params

    def fit(self, X, pre: pd.DataFrame, new: pd.DataFrame, unlabelled: pd.DataFrame):
        cov = Covariances(self.p["covariance"])
        C_pre = cov.transform(X[pre.index])
        self.W = centring_filters(cov.transform(X[unlabelled.index]))
        parts = [recentre(C_pre, centring_filters(C_pre))]
        ys, ws = [pre.label.to_numpy()], [np.ones(len(pre))]
        if len(new):
            parts.append(recentre(cov.transform(X[new.index]), self.W))
            ys.append(new.label.to_numpy())
            ws.append(np.full(len(new), float(self.p["target_weight"])))
        lr = self.p["logreg"]
        self.model = make_pipeline(
            TangentSpace(metric=self.p["tangent_space_metric"]),
            LogisticRegression(C=lr["C"], max_iter=lr["max_iter"]),
        )
        self.model.fit(np.concatenate(parts), np.concatenate(ys),
                       logisticregression__sample_weight=np.concatenate(ws))  # fmt: skip
        self.cov = cov
        return self

    def predict_proba(self, X):
        return self.model.predict_proba(recentre(self.cov.transform(X), self.W))


def subject_rows(subject: str, session: str, X, md: pd.DataFrame, proto, rct: dict) -> list[dict]:
    cal = proto.calibration
    pool_runs, test_runs = [int(r) for r in cal.pool_runs], [int(r) for r in cal.test_runs]
    pre = md[(md.session == "pre") & md.label.isin(CLASSES)]
    later = md[md.session == session]
    pool = later[later.run.isin(pool_runs)]
    test = later[later.run.isin(test_runs) & later.label.isin(CLASSES)]
    if set(pre.index) & set(test.index) or set(pool.index) & set(test.index):
        raise AssertionError("a test window in a training set")
    y = test.label.to_numpy()

    def bal(model) -> float:
        return score(y, model.predict_proba(X[test.index]), CLASSES)["bal_acc"]

    base = dict(subject=subject, session=session, group=md.group.iloc[0])
    # Independent of k: one row, stored at k = 0.
    rows = [dict(base, arm="pre_unchanged", k=0, draw="0", bal_acc=bal(fit_ts_lr(X, pre)))]
    k_all = max(cal.k_grid)
    for k in K_GRID:
        draws = ["0"] if k == 0 else [str(cal.seed_base + i) for i in range(cal.draws_classical)]
        for draw in draws:
            cd = draw_calibration_set(pool, [], [1, 2], k, draw, k_all=k_all)
            new = task_windows(pool.iloc[cd.labelled_idx], CLASSES)
            unl = pool.iloc[cd.unlabelled_idx] if k == 0 else new
            out = {"recentred": bal(Recentred(rct).fit(X, pre, new, unl))}
            if k > 0:
                out["new_only"] = bal(fit_ts_lr(X, new))
                out["pooled"] = bal(fit_ts_lr(X, pd.concat([pre, new])))
            rows += [dict(base, arm=a, k=k, draw=draw, bal_acc=v) for a, v in out.items()]
    return rows


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    paths, cfg, proto = get_paths(), load_data_config(), load_protocol_config()
    rct = method_params("rct_tslr", paths.configs)
    rows = []
    for subject in cfg.subjects.ids:
        sessions = cfg.sessions_for(subject)
        if "pre" not in sessions:
            continue
        X, md = load_windows(paths.epochs, cfg, subjects=[subject])
        md = md.reset_index(drop=True)
        for session in [s for s in LATER if s in sessions]:
            log.info("%s %s", subject, session)
            rows += subject_rows(subject, session, X, md, proto, rct)
    raw = pd.DataFrame(rows)
    per = raw.groupby(["subject", "session", "group", "arm", "k"], as_index=False).bal_acc.mean()
    per["git_sha"] = current_git_sha()
    summary = paths.results / "summary"
    per.to_csv(summary / "rq4_longitudinal.csv", index=False, float_format="%.6g")
    table = []
    for (session, arm, k), g in per.groupby(["session", "arm", "k"]):
        for population, h in [("all", g), *g.groupby("group")]:
            mean, lo, hi = bootstrap_ci(h.bal_acc.to_numpy())
            table.append(dict(session=session, arm=arm, k=k, population=population, n=len(h),
                              mean=mean, ci_lo=lo, ci_hi=hi))  # fmt: skip
    table = pd.DataFrame(table)
    table.to_csv(summary / "rq4_longitudinal_table.csv", index=False, float_format="%.6g")
    print(table[table.population == "all"].to_string(index=False))
    figure(table[table.population == "all"], paths.figures)


def figure(table: pd.DataFrame, figures) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from sixthfinger.viz.plots import save, use_style

    use_style()
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.8), sharey=True)
    colours = dict(zip(ARMS, ["0.4", "#ff7f0e", "#9467bd", "#2ca02c"], strict=True))
    for ax, session in zip(axes, LATER, strict=True):
        g = table[table.session == session]
        for arm in ARMS:
            a = g[g.arm == arm].sort_values("k")
            if arm == "pre_unchanged":
                ax.axhline(a["mean"].iloc[0], color=colours[arm], ls="--", lw=1, label=arm)
                continue
            ax.errorbar(a.k, a["mean"], yerr=[a["mean"] - a.ci_lo, a.ci_hi - a["mean"]],
                        color=colours[arm], marker="o", ms=3, lw=1.2, capsize=2,
                        label=arm)  # fmt: skip
        ax.axhline(1 / 3, color="0.7", lw=0.8)
        ax.set_xticks(K_GRID)
        ax.set_xlabel(f"trials per class from {session} runs 01-02")
        ax.set_title(f"tested on {session} runs 03-04", fontsize=8)
    axes[0].set_ylabel("balanced accuracy, three classes")
    axes[0].legend(frameon=False, fontsize=6)
    save(fig, figures, "rq4_longitudinal")


if __name__ == "__main__":
    main()
