"""What the exploratory analyses added after the results share (scripts/ex*_*.py).

None of them is confirmatory; each has a row in the protocol's deviation log. Their settings
are configs/experiments/ex*_*.yaml, fixed before any score on runs 03-04.
"""

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from sixthfinger.config import DataConfig
from sixthfinger.data.epochs import recut
from sixthfinger.evaluation.stats import bootstrap_ci, paired_test
from sixthfinger.paths import find_root, get_paths
from sixthfinger.preprocessing.alignment import align

# Development patients, left out in every sensitivity row.
DEV_SUBJECTS = ("sub-01", "sub-03")


def settings(name: str) -> dict:
    """An analysis's settings, configs/experiments/<name>.yaml."""
    return yaml.safe_load((get_paths().configs / "experiments" / f"{name}.yaml").read_text())


def pre_subjects(cfg: DataConfig) -> list[str]:
    """The patients with a usable `pre` session, in config order."""
    return [s for s in cfg.subjects.ids if "pre" in cfg.sessions_for(s)]


def channel_index(cfg: DataConfig, names) -> list[int]:
    keep = list(cfg.channels.keep)
    return [keep.index(c) for c in names]


def t1_baselines() -> dict[str, pd.Series]:
    """Committed per-patient AH vs SF values under `chrono` that the analyses compare with."""
    s = get_paths().summary
    rq1 = pd.read_csv(s / "rq1_subject_values.csv")
    rq1 = rq1[(rq1.task == "T1_ah_vs_sf") & (rq1.method == "ts_lr") & (rq1.protocol == "chrono")
              & (rq1.feature == "bandpower")]  # fmt: skip
    dl = pd.read_csv(s / "dl_baselines_subject_values.csv")
    dl = dl[(dl.task == "T1_ah_vs_sf") & (dl.protocol == "chrono")]
    vc = pd.read_csv(s / "rq4_visual_cue_decode.csv")
    vc = vc[(vc.task == "T1_ah_vs_sf") & (vc.channels == "central_14")]
    zs = pd.read_csv(s / "dl_zeroshot_subject_values.csv")
    zs = zs[zs.task == "T1_ah_vs_sf"]
    return {
        "ts_lr_pre": rq1[rq1.session == "pre"].set_index("subject").bal_acc,
        "ts_lr_post": rq1[rq1.session == "post"].set_index("subject").bal_acc,
        "eegnet_scratch_pre": dl.set_index("subject").bal_acc,
        "ts_lr_pre_central": vc.set_index("subject").bal_acc,
        "zeroshot_rest_pre": zs.set_index("subject").bal_acc,
    }


def crops_for(
    subject: str,
    X: np.ndarray,
    md: pd.DataFrame,
    cfg: DataConfig,
    processed: Path,
    starts: list[float],
    length: float,
) -> dict[float, tuple[np.ndarray, np.ndarray]]:
    """Per crop start: the rows of md the crop keeps, and their windows.

    A crop that crosses a boundary or a run edge is dropped by the cache's own rule. The crop
    that coincides with the cached window must equal it, which checks the recut.
    """
    out = {}
    for s in starts:
        keep, Xs = recut(md, cfg, processed, s, s + length)
        if (s, s + length) == (cfg.window.tmin, cfg.window.tmax):
            if not keep.all() or not np.array_equal(Xs, X):
                raise AssertionError(f"{subject}: the recut of the cached window differs")
            Xs = X
        out[s] = (np.flatnonzero(keep), Xs)
    return out


def crop_mean(model, crops: dict, rows: np.ndarray, n_rows: int, chans) -> np.ndarray:
    """Mean predict_proba of each window in `rows` over the crops it has."""
    total, count = np.zeros((n_rows, 2)), np.zeros(n_rows)
    for kept, Xs in crops.values():
        sel = np.isin(kept, rows)
        if not sel.any():
            continue
        Xc = Xs[sel] if chans is None else Xs[sel][:, chans]
        total[kept[sel]] += model.predict_proba(Xc)
        count[kept[sel]] += 1
    if (count[rows] < 1).any():
        raise AssertionError("a window without any crop")
    return total[rows] / count[rows, None]


def task_proba(m, X: np.ndarray, classes: list[int]) -> tuple[np.ndarray, int]:
    """`eegnet_ea_ft`'s renormalised task columns, computed from those columns' logits.

    Equal in exact arithmetic to the method's softmax-then-renormalise. On windows the
    network gives all float32 mass to a class outside the task (sub-11, runs 03-04: inputs
    up to about 1000 SD after alignment) that version divides 0 by 0. Returns the
    probabilities and how many windows the method itself could not answer.
    """
    import torch

    net = m.clf.module_
    net.eval()
    with torch.no_grad():
        logits = net(torch.from_numpy(m._x(align(X, m.R))))
    proba = torch.softmax(logits[:, classes].double(), dim=1).numpy()
    with np.errstate(invalid="ignore"):
        method = m.predict_proba(X)
    ok = np.isfinite(method).all(axis=1)
    if ok.any() and np.abs(method[ok] - proba[ok]).max() > 1e-4:
        raise AssertionError("the log-space task probabilities differ from eegnet_ea_ft's")
    return proba, int((~ok).sum())


def paired_row(name: str, arm: pd.Series, base: pd.Series, arm_label: str, base_label: str) -> dict:
    """One comparison over the patients both series have, and again without sub-01, sub-03.

    arm, base: one value per patient, indexed by subject. Differences are in points.
    """
    both = pd.concat([arm.rename("a"), base.rename("b")], axis=1).dropna()
    res = paired_test(both.a.to_numpy(), both.b.to_numpy())
    d = both.a - both.b
    no_dev = d.drop(list(DEV_SUBJECTS), errors="ignore")
    m20, lo20, hi20 = bootstrap_ci(no_dev.to_numpy())
    am, alo, ahi = bootstrap_ci(both.a.to_numpy())
    bm, blo, bhi = bootstrap_ci(both.b.to_numpy())
    return dict(
        comparison=name, arm=arm_label, baseline=base_label, n=res["n"],
        arm_mean=am, arm_ci_lo=alo, arm_ci_hi=ahi, base_mean=bm, base_ci_lo=blo, base_ci_hi=bhi,
        diff_points=res["mean_diff"] * 100, diff_ci_lo=res["ci_lo"] * 100,
        diff_ci_hi=res["ci_hi"] * 100, p_wilcoxon=res["p"],
        better=int((d > 0).sum()), worse=int((d < 0).sum()), tied=int((d == 0).sum()),
        n_without_dev=len(no_dev), diff_points_without_dev=m20 * 100,
        diff_ci_lo_without_dev=lo20 * 100, diff_ci_hi_without_dev=hi20 * 100,
    )  # fmt: skip


def class_weights(y: np.ndarray) -> np.ndarray:
    """1 / (windows of the window's class), so acting on every window gives balanced accuracy."""
    counts = pd.Series(y).value_counts()
    return 1.0 / counts.reindex(y).to_numpy(dtype=float)


def decisions(y: np.ndarray, P: np.ndarray, classes: list[int]):
    """Confidence, decided class and correctness of every window. P: (n, len(classes))."""
    pred = np.asarray(classes)[P.argmax(axis=1)]
    return P.max(axis=1), pred, pred == y


def acting(correct: np.ndarray, w: np.ndarray, act: np.ndarray) -> tuple[float, float, float]:
    """Accuracy on the acted windows (class-weighted, then plain) and the share acted."""
    if not act.any():
        return np.nan, np.nan, 0.0
    return (float((w[act] * correct[act]).sum() / w[act].sum()), float(correct[act].mean()),
            float(act.mean()))  # fmt: skip


def pick_threshold(
    conf: np.ndarray, correct: np.ndarray, w: np.ndarray, target: float, min_share: float
) -> dict:
    """The lowest confidence threshold whose accuracy when acting reaches `target`.

    Candidates are the distinct confidences that act on at least `min_share` of the windows.
    If none reaches the target, the one with the best accuracy when acting (the lower on a
    tie). Chosen on inner-validation decisions only, then applied unchanged to the test runs.
    """
    cands = []
    for t in np.unique(conf):
        act = conf >= t
        if act.mean() < min_share - 1e-12:
            continue
        acc_w, _, share = acting(correct, w, act)
        cands.append((float(t), share, acc_w))
    reached = [c for c in cands if c[2] >= target - 1e-12]
    if reached:
        t, share, acc = min(reached, key=lambda c: c[0])
    else:
        best = max(c[2] for c in cands)
        t, share, acc = min((c for c in cands if c[2] == best), key=lambda c: c[0])
    return dict(threshold=t, inner_share=share, inner_acc=acc, reached_target=bool(reached))


def coverage(
    conf: np.ndarray, correct: np.ndarray, w: np.ndarray, shares
) -> list[tuple[float, float, float]]:
    """Accuracy when acting on each share of the most confident windows (rounded up)."""
    order = np.argsort(-conf, kind="stable")
    out = []
    for s in shares:
        top = np.zeros(len(conf), bool)
        top[order[: math.ceil(s * len(conf) - 1e-9)]] = True
        acc_w, acc_plain, _ = acting(correct, w, top)
        out.append((s, acc_w, acc_plain))
    return out


def fire_rates(pred: np.ndarray, conf: np.ndarray, threshold: float, command: int):
    """Share of windows decided as `command`, and of those that also clear the threshold."""
    fire = pred == command
    return float(fire.mean()), float((fire & (conf >= threshold)).mean())


def source_commit(path: Path) -> str:
    """Short commit that last changed a tracked file; refuses one with uncommitted changes."""
    git = ["git", "-C", str(find_root())]
    kw = {"capture_output": True, "text": True, "check": True}
    if subprocess.run([*git, "status", "--porcelain", "--", str(path)], **kw).stdout.strip():
        raise SystemExit(f"{path.name} differs from its last commit; commit it first")
    sha = subprocess.run([*git, "log", "-n1", "--format=%h", "--", str(path)], **kw).stdout.strip()
    if not sha:
        raise SystemExit(f"{path.name} was never committed")
    return sha


def carry(src: Path, dest: Path, columns: list[str], extra: dict | None = None) -> pd.DataFrame:
    """Copy an expensive part's per-fit values, adding the commit that holds them.

    The copy must have exactly `columns`, the ones the part writes itself.
    """
    df = pd.read_csv(src)
    if list(df.columns) != columns:
        raise SystemExit(f"{src.name}: columns {list(df.columns)}, expected {columns}")
    for k, v in (extra or {}).items():
        df[k] = v
    df["source_commit"] = source_commit(src)
    dest.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(dest, index=False, float_format="%.10g")
    return df


def table_diff(new: pd.DataFrame, old: pd.DataFrame, ignore=("git_sha", "source_commit")) -> dict:
    """Cell by cell, every column of `old` against `new`, in row order."""
    cols = [c for c in old.columns if c not in ignore]
    missing = [c for c in cols if c not in new.columns]
    out = dict(rows=len(new), rows_before=len(old), columns=len(cols),
               missing_columns=";".join(missing), cells_differing=np.nan,
               max_abs_diff=np.nan, identical=False)  # fmt: skip
    if missing or len(new) != len(old):
        return out
    n_diff, worst = 0, 0.0
    for c in cols:
        a, b = new[c].reset_index(drop=True), old[c].reset_index(drop=True)
        same_nan = a.isna() & b.isna()
        numeric = all(
            pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s) for s in (a, b)
        )
        if numeric:
            d = (a.astype(float) - b.astype(float)).abs()
            n_diff += int((~same_nan & ~(d == 0)).sum())
            if (~same_nan).any():
                worst = max(worst, float(np.nan_to_num(d[~same_nan], nan=np.inf).max()))
        else:
            n_diff += int((~same_nan & (a.astype(str) != b.astype(str))).sum())
    out.update(cells_differing=n_diff, max_abs_diff=worst, identical=n_diff == 0)
    return out


def leaves(obj, prefix: str = "") -> list[tuple[str, object]]:
    """Every scalar of a nested JSON value, with its key path."""
    if isinstance(obj, dict):
        return [x for k, v in obj.items() for x in leaves(v, f"{prefix}/{k}")]
    if isinstance(obj, list | tuple):
        return [x for i, v in enumerate(obj) for x in leaves(v, f"{prefix}[{i}]")]
    return [(prefix, obj)]


def json_diff(new, old) -> dict:
    """Leaf by leaf in order; keys may have been renamed, values may not."""
    # The commit a check ran at is provenance, not a result.
    a, b = ([x for x in leaves(v) if not x[0].rsplit("/", 1)[-1].startswith("git")]
            for v in (new, old))  # fmt: skip
    out = dict(rows=len(a), rows_before=len(b), columns=1, missing_columns="",
               cells_differing=np.nan, max_abs_diff=np.nan, identical=False)  # fmt: skip
    if len(a) != len(b):
        return out
    n_diff, worst = 0, 0.0
    for (_, x), (_, y) in zip(a, b, strict=True):
        if isinstance(x, int | float) and isinstance(y, int | float) and not isinstance(x, bool):
            if not (math.isnan(x) and math.isnan(y)):
                worst = max(worst, abs(x - y))
                n_diff += x != y
        else:
            n_diff += x != y
    out.update(cells_differing=int(n_diff), max_abs_diff=worst, identical=n_diff == 0)
    return out


def repro_table(
    prefix: str, research: Path, files: dict[str, Path], ignore=("git_sha", "source_commit")
) -> pd.DataFrame:
    """Every promoted output against the file of the same name in the exploratory run.

    files: research file name -> promoted path. Provenance columns are not compared.
    """
    rows = []
    for name, path in files.items():
        old = research / name
        if not old.exists() or not path.exists():
            gone = "before" if not old.exists() else "now"
            rows.append(dict(file=path.name, before=name, identical=False, note=f"missing {gone}"))
            continue
        if name.endswith(".json"):
            res = json_diff(json.loads(path.read_text()), json.loads(old.read_text()))
        else:
            res = table_diff(pd.read_csv(path), pd.read_csv(old), ignore)
        skipped = ", ".join(sorted(set(ignore) - {"git_sha", "source_commit"}))
        note = f"not compared: {skipped}" if skipped else ""
        rows.append(dict(file=path.name, before=name, **res, note=note))
    out = pd.DataFrame(rows)
    out.insert(0, "analysis", prefix)
    return out


def settings_diff(promoted: dict, before: dict) -> dict:
    """The YAML against the settings file fixed before scoring: leaves that changed, by kind."""
    a, b = leaves(promoted), leaves(before)
    keys_a, keys_b = [k for k, _ in a], [k for k, _ in b]
    changed = [k for (k, x), (_, y) in zip(a, b, strict=False) if x != y]
    non_text = [k for (k, x), (_, y) in zip(a, b, strict=False)
                if x != y and not (isinstance(x, str) and isinstance(y, str))]  # fmt: skip
    return dict(file="settings", before="settings", rows=len(a), rows_before=len(b),
                columns=1, missing_columns="", cells_differing=len(changed),
                max_abs_diff=np.nan, identical=keys_a == keys_b and not changed,
                note=("same keys; " if keys_a == keys_b else "keys differ; ")
                + (f"text renamed at {'; '.join(changed)}" if changed else "")
                + (f"; NON-TEXT CHANGES at {'; '.join(non_text)}" if non_text else ""))  # fmt: skip
