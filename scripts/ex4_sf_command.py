"""Exploratory, added after the results: the sixth finger as its own command (sixth finger vs
rest), acting only when sure, and its overlap with the affected hand.

One part at a time, in this order:

uv run python scripts/ex4_sf_command.py --part inner_classical  # learn run 01, check run 02...
uv run python scripts/ex4_sf_command.py --part inner_eegnet     # ...and the reverse
uv run python scripts/ex4_sf_command.py --part select   # headline arm and thresholds, runs 01-02
uv run python scripts/ex4_sf_command.py --part test_classical   # learn runs 01-02, test 03-04
uv run python scripts/ex4_sf_command.py --part test_eegnet
uv run python scripts/ex4_sf_command.py --part summary

Settings: configs/experiments/ex4_sf_command.yaml, fixed before any score. `select` chooses the
headline arm from runs 01-02 alone and appends it to the settings; it refuses once any score on
runs 03-04 exists, unless the settings already hold a choice, which it then only checks. The
test parts refuse to run without it. Every window's probabilities go to
results/runs/ex4_sf_command/ and `summary` rebuilds every table from them without refitting.
The EEGNet parts take about 80 minutes: `--part carry --research DIR` takes their predictions
from the exploratory run in DIR with the commit that holds them, the EEGNet parts with
`--subjects` re-run a few patients beside them, and `--part repro --research DIR` compares
every output. Writes results/summary/ex4_sf_command_*.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch

import sixthfinger.models  # noqa: F401  (registers every method)
from sixthfinger.config import load_data_config
from sixthfinger.data.channels import CENTRAL_14
from sixthfinger.data.epochs import load_windows
from sixthfinger.evaluation import exploratory as ex
from sixthfinger.evaluation.leakage import assert_no_leakage
from sixthfinger.evaluation.metrics import score
from sixthfinger.evaluation.runner import method_params
from sixthfinger.evaluation.stats import bootstrap_ci
from sixthfinger.models.registry import Batch, make_method
from sixthfinger.paths import current_git_sha, get_paths
from sixthfinger.preprocessing.alignment import align

NAME = "ex4_sf_command"
SETTINGS = get_paths().configs / "experiments" / f"{NAME}.yaml"
CONFIG = ex.settings(NAME)
RUNS_DIR = get_paths().runs / NAME
REST, AH, SF = 0, 1, 2
PCOL = {REST: "p_rest", AH: "p_ah", SF: "p_sf"}
FOLDS = {
    "inner": {k: tuple(v) for k, v in CONFIG["inner_validation"]["folds"].items()},
    "test": {"final": (CONFIG["train_runs"], CONFIG["test_runs"])},
}
PART1 = CONFIG["headline"]["candidates"]
EEGNET = [a for a, s in CONFIG["arms"].items() if s["method"] == "eegnet_ea_ft"]
CLASSICAL = [a for a, s in CONFIG["arms"].items() if s["method"] != "eegnet_ea_ft"]
# A commit can be all digits, which pandas would otherwise read back as a number.
PROVENANCE = {"git_sha": str, "source_commit": str}
PRED_COLUMNS = ["subject", "task", "arm", "seed", "fold", "n_train", "fit_seconds",
                "n_registry_nan", "n_dropped_crops", "kind", "trial_uid", "run", "label",
                "p_rest", "p_ah", "p_sf"]  # fmt: skip

log = logging.getLogger(NAME)


def out(name: str) -> Path:
    return get_paths().summary / f"{NAME}_{name}"


def pred_path(fold_set: str, kind: str) -> Path:
    return RUNS_DIR / f"pred_{fold_set}_{kind}.csv"


def setup_logging() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S")
    for h in (logging.StreamHandler(), logging.FileHandler(RUNS_DIR / "run.log")):
        h.setFormatter(fmt)
        log.addHandler(h)
    log.setLevel(logging.INFO)


def headline_choice() -> dict | None:
    return CONFIG.get("headline_choice")


def test_files() -> list[Path]:
    return sorted(RUNS_DIR.glob("pred_test_*.csv"))


def machine_ok() -> None:
    """Stop a part, keeping what it has, when swap or free disk pass the settings' limits."""
    lim = CONFIG["machine"]
    swap = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True,
                          check=False).stdout  # fmt: skip
    m = re.search(r"used = ([\d.]+)([MG])", swap)
    swap_gb = float(m.group(1)) / (1024 if m.group(2) == "M" else 1) if m else 0.0
    free_gb = shutil.disk_usage(RUNS_DIR).free / 1e9
    if swap_gb > lim["max_swap_gb"] or free_gb < lim["min_free_disk_gb"]:
        raise SystemExit(f"paused: swap {swap_gb:.1f} GB, free disk {free_gb:.1f} GB")


def pre_subjects() -> list[str]:
    return ex.pre_subjects(load_data_config())


def patient(subject: str) -> tuple[np.ndarray, pd.DataFrame]:
    """Every cached pre window of one patient (REST, AH, SF), X: (n, 40, 1000) volts."""
    X, md = load_windows(get_paths().epochs, load_data_config(), subjects=[subject],
                         sessions=["pre"])  # fmt: skip
    return X, md.reset_index(drop=True)


def channel_index(name: str) -> list[int] | None:
    cfg = load_data_config()
    central = ex.channel_index(cfg, CENTRAL_14)
    if name == "all_40":
        return None
    if name == "central_14":
        return central
    if name == "central_14_zeroed":
        return [i for i in range(len(cfg.channels.keep)) if i not in central]
    raise ValueError(name)


def rows_of(md: pd.DataFrame, runs, labels) -> np.ndarray:
    return md.index[md.run.isin(runs) & md.label.isin(labels)].to_numpy()


def pred_rows(base: dict, md: pd.DataFrame, idx, proba, classes, kind: str) -> list[dict]:
    rows = []
    for k, i in enumerate(idx):
        r = dict(base, kind=kind, trial_uid=md.trial_uid[i], run=int(md.run[i]),
                 label=int(md.label[i]))  # fmt: skip
        for c, col in PCOL.items():
            r[col] = float(proba[k, classes.index(c)]) if c in classes else np.nan
        rows.append(r)
    return rows


def splits(md: pd.DataFrame, task: str, tr_runs, ev_runs, with_probe: bool):
    """Training and scored rows of a task; with_probe adds the AH windows of the scored runs."""
    classes = CONFIG["tasks"][task]
    tr, ev = rows_of(md, tr_runs, classes), rows_of(md, ev_runs, classes)
    probe = rows_of(md, ev_runs, [AH]) if with_probe else np.array([], int)
    return classes, tr, ev, probe


def save_preds(rows: list[dict], path: Path) -> None:
    """Every window's probabilities, each row with the commit that made it (resumes keep theirs)."""
    df = pd.DataFrame(rows)
    sha = current_git_sha()
    df["git_sha"] = df["git_sha"].fillna(sha) if "git_sha" in df else sha
    df.to_csv(path, index=False, float_format="%.10g")


def run_part(fold_set: str, kind: str, per_patient, subjects: list[str] | None) -> None:
    """Resumable loop over patients; the file appears only when all 22 are done.

    With `subjects`, those patients alone, into a re-run file beside the stored predictions.
    """
    final = pred_path(fold_set, kind)
    if subjects:
        rows = []
        for subject in subjects:
            rows += per_patient(subject, fold_set)
        save_preds(rows, RUNS_DIR / f"rerun_{final.name}")
        return
    partial = final.with_suffix(".partial.csv")
    if final.exists():
        log.info("%s exists; nothing to do", final.name)
        return
    rows = pd.read_csv(partial, dtype=PROVENANCE).to_dict("records") if partial.exists() else []
    done = {r["subject"] for r in rows}
    for subject in pre_subjects():
        if subject in done:
            continue
        machine_ok()
        t0 = time.perf_counter()
        new = per_patient(subject, fold_set)
        rows += new
        save_preds(rows, partial)
        log.info("%s %s %s: %d rows, %.1f s", fold_set, kind, subject, len(new),
                 time.perf_counter() - t0)  # fmt: skip
    if {r["subject"] for r in rows} >= set(pre_subjects()):
        partial.replace(final)
        log.info("wrote %s (%d rows)", final.name, len(rows))


def classical_patient(subject: str, fold_set: str) -> list[dict]:
    w = CONFIG["arm_W"]
    paths, cfg = get_paths(), load_data_config()
    X, md = patient(subject)
    crops = ex.crops_for(subject, X, md, cfg, paths.processed, w["crop_starts_s"],
                         w["crop_length_s"])  # fmt: skip
    n_drop = {s: int(len(md) - len(r)) for s, (r, _) in crops.items()}
    rows = []
    for fold, (tr_runs, ev_runs) in FOLDS[fold_set].items():
        fitted = {}
        for arm in CLASSICAL:
            s = CONFIG["arms"][arm]
            probe = fold_set == "test" and s["task"] == "T3_sf_vs_rest"
            classes, tr, ev, ah = splits(md, s["task"], tr_runs, ev_runs, probe)
            assert_no_leakage(md.iloc[tr], md.iloc[np.concatenate([ev, ah])])
            ch = channel_index(s["channels"])
            key = (s["task"], s["method"], s["channels"])
            if key not in fitted:
                t0 = time.perf_counter()
                Xt = X[tr] if ch is None else X[tr][:, ch]
                params = method_params(s["method"], paths.configs)
                m = make_method(s["method"], n_classes=len(classes), **params)
                m.fit(Batch(Xt, md.label.to_numpy()[tr], md.iloc[tr]))
                if list(m.pipe[-1].classes_) != classes:
                    raise AssertionError(f"{arm}: class order differs from the task's")
                fitted[key] = (m, time.perf_counter() - t0)
            m, secs = fitted[key]
            base = dict(subject=subject, task=s["task"], arm=arm, seed=-1, fold=fold,
                        n_train=len(tr), fit_seconds=secs, n_registry_nan=0,
                        n_dropped_crops=json.dumps(n_drop) if s["crops"] else "")  # fmt: skip
            for idx, kind in ((ev, "task"), (ah, "probe_ah")):
                if not len(idx):
                    continue
                if s["crops"]:
                    proba = ex.crop_mean(m, crops, idx, len(md), ch)
                else:
                    proba = m.predict_proba(X[idx] if ch is None else X[idx][:, ch])
                rows += pred_rows(base, md, idx, proba, classes, kind)
    del X, crops
    return rows


def ea_ft(classes: list[int]):
    paths = get_paths()
    params = method_params("eegnet_ea_ft", paths.configs) | {"device": CONFIG["arm_T"]["device"]}
    return make_method(
        "eegnet_ea_ft", n_classes=len(classes), classes=classes,
        models_dir=paths.models / "pretrained", mirror=False, **params,
    )  # fmt: skip


def eegnet_patient(subject: str, fold_set: str) -> list[dict]:
    torch.set_num_threads(CONFIG["arm_T"]["torch_threads"])
    X_all, md = patient(subject)
    y = md.label.to_numpy()
    rows = []
    for arm in EEGNET:
        s = CONFIG["arms"][arm]
        X = X_all
        others = None
        if s["channels"] == "central_14_zeroed":
            others = channel_index("central_14_zeroed")
            X = X_all.copy()
            X[:, others] = 0.0
        for fold, (tr_runs, ev_runs) in FOLDS[fold_set].items():
            probe = fold_set == "test" and s["task"] == "T3_sf_vs_rest"
            classes, tr, ev, ah = splits(md, s["task"], tr_runs, ev_runs, probe)
            train_md = md.iloc[tr]
            assert_no_leakage(train_md, md.iloc[np.concatenate([ev, ah])], unlabelled=train_md)
            for seed in CONFIG["arm_T"]["seeds"]:
                t0 = time.perf_counter()
                labelled, unlabelled = Batch(X[tr], y[tr], train_md), Batch(X[tr], None, train_md)
                m = ea_ft(classes).fit(labelled, unlabelled=unlabelled, seed=seed)
                secs = time.perf_counter() - t0
                if others is not None:
                    aligned = np.abs(align(X[tr], m.R))
                    if aligned[:, others].max() > 1e-6 * aligned.max():
                        raise AssertionError(f"{subject}: alignment moved signal into the zeros")
                for idx, kind in ((ev, "task"), (ah, "probe_ah")):
                    if not len(idx):
                        continue
                    proba, n_nan = ex.task_proba(m, X[idx], classes)
                    base = dict(subject=subject, task=s["task"], arm=arm, seed=seed, fold=fold,
                                n_train=len(tr), fit_seconds=secs, n_registry_nan=n_nan,
                                n_dropped_crops="")  # fmt: skip
                    rows += pred_rows(base, md, idx, proba, classes, kind)
        log.info("  %s %s %s done", fold_set, subject, arm)
    return rows


def predictions(fold_set: str) -> pd.DataFrame:
    frames = []
    for kind in ("classical", "eegnet"):
        path = pred_path(fold_set, kind)
        if not path.exists():
            raise SystemExit(f"{path.name} missing: run --part {fold_set}_{kind} first")
        frames.append(pd.read_csv(path, dtype=PROVENANCE))
    return pd.concat(frames, ignore_index=True)


def task_view(g: pd.DataFrame, classes: list[int]) -> tuple[np.ndarray, np.ndarray]:
    """Labels and (n, n_classes) probabilities of a group's task windows."""
    t = g[g.kind == "task"]
    return t.label.to_numpy(), t[[PCOL[c] for c in classes]].to_numpy()


def fold_scores(pred: pd.DataFrame) -> pd.DataFrame:
    """Balanced accuracy of every fit: one row per arm, seed, fold and patient."""
    rows = []
    for (arm, seed, fold, subject), g in pred.groupby(["arm", "seed", "fold", "subject"]):
        classes = CONFIG["tasks"][CONFIG["arms"][arm]["task"]]
        y, P = task_view(g, classes)
        rows.append(dict(arm=arm, seed=seed, fold=fold, subject=subject,
                         bal_acc=score(y, P, classes)["bal_acc"], n=len(y),
                         n_registry_nan=int(g.n_registry_nan.max())))  # fmt: skip
    return pd.DataFrame(rows)


def inner_choice(inner: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, str]:
    """Inner-validation means, per patient and per arm, and the headline arm by the rule."""
    missing = {(a, s) for a in CONFIG["arms"] for s in pre_subjects()} - set(
        zip(inner.arm, inner.subject, strict=True)
    )
    if missing:
        raise SystemExit(f"inner predictions incomplete, e.g. {sorted(missing)[:3]}")
    fs = fold_scores(inner)
    per_patient = fs.pivot_table(index="subject", columns="arm", values="bal_acc", aggfunc="mean")
    sel = []
    for arm in CONFIG["arms"]:
        mean, lo, hi = bootstrap_ci(per_patient[arm].to_numpy())
        sel.append(dict(arm=arm, task=CONFIG["arms"][arm]["task"], inner_mean=mean,
                        inner_ci_lo=lo, inner_ci_hi=hi, n=int(per_patient[arm].notna().sum()),
                        headline_candidate=arm in PART1))  # fmt: skip
    sel = pd.DataFrame(sel)
    cand = sel[sel.headline_candidate].set_index("arm").inner_mean.reindex(PART1)
    if cand.isna().any() or per_patient.isna().any().any():
        raise SystemExit("an inner-validation value is missing: the headline cannot be chosen")
    headline = str(cand.index[int(np.argmax(cand.to_numpy()))])  # argmax keeps the first tie
    return sel, per_patient, cand, headline


def part_select() -> None:
    recorded = headline_choice()
    if recorded is None and test_files():
        raise SystemExit("runs 03-04 already scored: the headline can no longer be chosen")
    inner = predictions("inner")
    sel, per_patient, cand, headline = inner_choice(inner)
    sel.to_csv(out("selection.csv"), index=False, float_format="%.6g")
    per_patient.reset_index().to_csv(out("selection_per_patient.csv"), index=False,
                                     float_format="%.6g")  # fmt: skip
    r = CONFIG["arm_R"]
    thr = []
    for (arm, seed, subject), g in inner.groupby(["arm", "seed", "subject"]):
        classes = CONFIG["tasks"][CONFIG["arms"][arm]["task"]]
        y, P = task_view(g, classes)
        conf, _, correct = ex.decisions(y, P, classes)
        picked = ex.pick_threshold(conf, correct, ex.class_weights(y), r["target"], r["min_share"])
        thr.append(dict(arm=arm, seed=seed, subject=subject, n_inner=len(y), **picked))
    pd.DataFrame(thr).to_csv(out("thresholds.csv"), index=False, float_format="%.10g")
    log.info("inner-validation means:\n%s", sel.round(4).to_string(index=False))
    means = {a: float(v) for a, v in cand.items()}
    if recorded is not None:
        # The choice was made before any test score; a re-run may only confirm it.
        if recorded["arm"] != headline or recorded["inner_means"] != means:
            raise SystemExit(f"recomputed headline {headline} {means} differs from the recorded "
                             f"{recorded['arm']} {recorded['inner_means']}")  # fmt: skip
        log.info("headline arm %s, as recorded on %s", headline, recorded["chosen_at"])
        return
    choice = {
        "arm": headline,
        "inner_mean": float(cand[headline]),
        "inner_means": means,
        "chosen_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "files": f"{NAME}_selection.csv, {NAME}_selection_per_patient.csv, "
        f"{NAME}_thresholds.csv (runs 01-02 only)",
    }
    import yaml

    with SETTINGS.open("a") as f:
        f.write(yaml.safe_dump({"headline_choice": choice}, sort_keys=False, width=96))
    log.info("headline arm: %s, appended to %s", headline, SETTINGS.name)


def require_headline() -> None:
    if headline_choice() is None or not out("thresholds.csv").exists():
        raise SystemExit("no headline in the settings yet: run --part select first")


def committed() -> dict[str, pd.Series]:
    s = get_paths().summary
    rq1 = pd.read_csv(s / "rq1_subject_values.csv")
    rq1 = rq1[(rq1.protocol == "chrono") & (rq1.session == "pre") & (rq1.feature == "bandpower")]
    vc = pd.read_csv(s / "rq4_visual_cue_decode.csv")

    def pick(df, **kw):
        for k, v in kw.items():
            df = df[df[k] == v]
        return df.set_index("subject").bal_acc

    return {
        "csp_lda": pick(rq1, task="T3_sf_vs_rest", method="csp_lda"),
        "ts_lr": pick(rq1, task="T3_sf_vs_rest", method="ts_lr"),
        "ts_lr (rq4 all_40)": pick(vc, task="T3_sf_vs_rest", channels="all_40"),
        "ts_lr_c14": pick(vc, task="T3_sf_vs_rest", channels="central_14"),
        "T1_ts_lr": pick(rq1, task="T1_ah_vs_sf", method="ts_lr"),
        "T2_ts_lr": pick(rq1, task="T2_rest_ah_sf", method="ts_lr"),
    }


def at_least(v: pd.Series, level: float) -> int:
    return int((v.dropna() >= level - 1e-9).sum())


def describe(name: str, v: pd.Series, section: str, **extra) -> dict:
    v = v.dropna()
    mean, lo, hi = bootstrap_ci(v.to_numpy()) if len(v) else (np.nan, np.nan, np.nan)
    return dict(section=section, row=name, n=len(v), mean=mean, ci_lo=lo, ci_hi=hi,
                n_ge_80=at_least(v, 0.8), n_ge_90=at_least(v, 0.9), **extra)  # fmt: skip


def compare(name: str, a: pd.Series, b: pd.Series, a_label: str, b_label: str) -> dict:
    row = ex.paired_row(name, a, b, a_label, b_label)
    both = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    row |= dict(arm_n_ge_80=at_least(both.a, 0.8), arm_n_ge_90=at_least(both.a, 0.9),
                base_n_ge_80=at_least(both.b, 0.8), base_n_ge_90=at_least(both.b, 0.9))  # fmt: skip
    return row


def gate_tables(test: pd.DataFrame, thr: pd.DataFrame):
    """Per arm, seed and patient: the gate on runs 03-04, the coverage curve and fire rates."""
    thr = thr.set_index(["arm", "seed", "subject"]).threshold
    shares = np.round(np.arange(1, 11) / 10, 1)
    gate, cover, fires = [], [], []
    for (arm, seed, subject), g in test.groupby(["arm", "seed", "subject"]):
        task = CONFIG["arms"][arm]["task"]
        classes = CONFIG["tasks"][task]
        y, P = task_view(g, classes)
        conf, pred, correct = ex.decisions(y, P, classes)
        w = ex.class_weights(y)
        t = thr[(arm, seed, subject)]
        act = conf >= t
        acc_w, acc_plain, share = ex.acting(correct, w, act)
        gate.append(dict(arm=arm, seed=seed, subject=subject, threshold=t, acc_w=acc_w,
                         acc_plain=acc_plain, share=share, n_acted=int(act.sum()), n=len(y),
                         bal_acc_all=score(y, P, classes)["bal_acc"],
                         **{f"share_acted_label{c}": float(act[y == c].mean())
                            for c in classes}))  # fmt: skip
        for s, a_w, a_p in ex.coverage(conf, correct, w, shares):
            cover.append(dict(arm=arm, seed=seed, subject=subject, share=s, acc_w=a_w,
                              acc_plain=a_p))  # fmt: skip
        if task == "T3_sf_vs_rest":
            pr = g[g.kind == "probe_ah"]
            P_ah = pr[[PCOL[c] for c in classes]].to_numpy()
            conf_ah, pred_ah, _ = ex.decisions(pr.label.to_numpy(), P_ah, classes)
            row = dict(arm=arm, seed=seed, subject=subject, n_ah=len(pr))
            for name, lab_pred, lab_conf in (("ah", pred_ah, conf_ah),
                                             ("rest", pred[y == REST], conf[y == REST]),
                                             ("sf", pred[y == SF], conf[y == SF])):  # fmt: skip
                row[f"fire_{name}"], row[f"fire_{name}_gated"] = ex.fire_rates(
                    lab_pred, lab_conf, t, SF
                )
            fires.append(row)
    gate, cover, fires = pd.DataFrame(gate), pd.DataFrame(cover), pd.DataFrame(fires)
    # eegnet arms: one value per patient, the mean over seeds (seeds without an action skipped).
    gate_p = gate.groupby(["arm", "subject"]).agg(
        threshold=("threshold", "mean"), acc_w=("acc_w", "mean"), acc_plain=("acc_plain", "mean"),
        share=("share", "mean"), bal_acc_all=("bal_acc_all", "mean"),
        n_seeds_no_action=("n_acted", lambda v: int((v == 0).sum())),
    )  # fmt: skip
    cover_p = cover.groupby(["arm", "subject", "share"])[["acc_w", "acc_plain"]].mean()
    fires_p = fires.groupby(["arm", "subject"]).mean(numeric_only=True).drop(columns="seed")
    return gate, gate_p, cover_p, fires_p


def raw_cache_codes() -> tuple[int, list[str]]:
    files = sorted((get_paths().derived / "raw_windows").glob("sub-*_pre_*.npz"))
    codes: set[str] = set()
    for f in files:
        with np.load(f) as z:
            codes |= set(z["codes"].astype(str).tolist())
    return len(files), sorted(codes)


def max_diff(a: pd.Series, b: pd.Series) -> list[float]:
    """Max abs difference, raw and with ours rounded to 6 significant digits.

    The committed files store 6 significant digits, so the rounded value is the exact test.
    """
    both = pd.concat([a.rename("a"), b.rename("b")], axis=1)
    if both.isna().any().any():
        return [float("nan"), float("nan")]
    rounded = both.a.map(lambda v: float(f"{v:.6g}"))
    return [float((both.a - both.b).abs().max()), float((rounded - both.b).abs().max())]


def part_summary() -> None:
    choice = headline_choice()
    if choice is None:
        raise SystemExit("no headline chosen")
    headline = choice["arm"]
    test = predictions("test")
    inner = predictions("inner")
    inner_sel = pd.read_csv(out("selection.csv")).set_index("arm")
    thr = pd.read_csv(out("thresholds.csv"))
    fs = fold_scores(test)
    seed_sd = fs[fs.seed >= 0].groupby(["arm", "subject"]).bal_acc.std().groupby("arm").mean()
    test_pp = fs.pivot_table(index="subject", columns="arm", values="bal_acc", aggfunc="mean")
    c = committed()
    checks: dict = {}

    tail = "(max abs diff over 22 patients: raw, rounded to 6 digits as stored)"
    for arm, key in (("csp_lda", "csp_lda"), ("ts_lr", "ts_lr"), ("ts_lr", "ts_lr (rq4 all_40)"),
                     ("ts_lr_c14", "ts_lr_c14"), ("T1_ts_lr", "T1_ts_lr"),
                     ("T2_ts_lr", "T2_ts_lr")):  # fmt: skip
        checks[f"{arm} vs committed {key} {tail}"] = max_diff(test_pp[arm], c[key])
    vb = pd.read_csv(get_paths().summary / "ex1_transfer_ah_sf_values_B.csv")
    vb = vb[vb.row == "finetuned"].set_index(["subject", "seed"]).bal_acc
    ours = fs[fs.arm == "T1_ea_ft"].set_index(["subject", "seed"]).bal_acc
    checks[f"T1_ea_ft vs ex1_transfer_ah_sf values_B finetuned, per seed {tail}"] = max_diff(
        ours, vb
    )
    n_files, codes = raw_cache_codes()
    checks["raw-window cache files (data/derived/raw_windows)"] = n_files
    checks["raw-window cache cue codes"] = codes
    checks["arm S run (cache holds REST, code 1)"] = "1" in codes
    for arm in EEGNET:
        checks[f"{arm} mean seed SD (points)"] = float(seed_sd[arm] * 100)
    nan_fits = pd.concat([fold_scores(inner), fs])
    nan_fits = nan_fits[nan_fits.n_registry_nan > 0]
    checks["eegnet fits with windows the registry answers NaN (inner + test)"] = len(nan_fits)
    checks["those fits (arm, fold, subject, seed)"] = sorted(
        f"{r.arm} {r.fold} {r.subject} seed {r.seed}" for r in nan_fits.itertuples()
    )
    dropped = test[(test.n_dropped_crops.fillna("") != "") & (test.fold == "final")]
    drops = dropped.groupby("subject").n_dropped_crops.first().map(json.loads)
    checks["W crops dropped over each patient's pre windows (patients with any, in total)"] = [
        int(sum(any(v.values()) for v in drops)),
        int(sum(sum(v.values()) for v in drops)),
    ]
    windows = test[(test.fold == "final") & (test.kind == "task")]
    windows = windows[windows.seed.isin([-1, 0])].drop_duplicates(["task", "trial_uid", "label"])
    counts = windows.groupby(["task", "label"]).size()
    checks["test windows per task and label"] = {
        f"{t} label {lab}": int(n) for (t, lab), n in counts.items()
    }
    probes = test[(test.kind == "probe_ah") & (test.arm == "ts_lr")]
    checks["AH windows of runs 03-04 passed through each T3 command"] = len(probes)
    checks["headline arm (by inner validation)"] = headline
    checks["git sha at summary"] = current_git_sha()

    gate, gate_p, cover_p, fires_p = gate_tables(test, thr)
    thr_reached = thr.groupby(["arm", "subject"]).reached_target.mean()

    table = []
    for arm in PART1:
        table.append(describe(arm, test_pp[arm], "part1",
                              inner_mean=inner_sel.inner_mean[arm],
                              seed_sd_points=float(seed_sd.get(arm, np.nan)) * 100,
                              headline=arm == headline))  # fmt: skip
    gp = gate_p.loc[headline]
    share_m, share_lo, share_hi = bootstrap_ci(gp.share.to_numpy())
    table.append(describe(f"R ({headline}), accuracy when acting", gp.acc_w, "arm_R",
                          share_mean=share_m, share_ci_lo=share_lo, share_ci_hi=share_hi,
                          n_patients_no_action=int(gp.acc_w.isna().sum()),
                          n_patients_inner_reached_90=int((thr_reached.loc[headline] == 1).sum()),
                          headline=True))  # fmt: skip
    table.append(describe(f"R ({headline}), plain accuracy when acting", gp.acc_plain, "arm_R"))
    for arm in PART1:
        f = fires_p.loc[arm]
        for col in ("fire_ah", "fire_rest", "fire_sf", "fire_ah_gated", "fire_rest_gated",
                    "fire_sf_gated"):  # fmt: skip
            table.append(describe(f"{arm} {col}", f[col], "part2_fires", headline=arm == headline))
    for task_arms, section in ((("T1_ts_lr", "T1_ea_ft"), "part2_T1"),
                               (("T2_ts_lr", "T2_ea_ft"), "part2_T2")):  # fmt: skip
        for arm in task_arms:
            g = gate_p.loc[arm]
            sm, slo, shi = bootstrap_ci(g.share.to_numpy())
            reached = int((thr_reached.loc[arm] == 1).sum())
            sd = float(seed_sd.get(arm, np.nan)) * 100
            table.append(describe(f"{arm}, all windows", test_pp[arm], section, seed_sd_points=sd,
                                  inner_mean=inner_sel.inner_mean[arm]))  # fmt: skip
            table.append(describe(f"{arm}, accuracy when acting", g.acc_w, section,
                                  share_mean=sm, share_ci_lo=slo, share_ci_hi=shi,
                                  n_patients_no_action=int(g.acc_w.isna().sum()),
                                  n_patients_inner_reached_90=reached))  # fmt: skip
            table.append(describe(f"{arm}, plain accuracy when acting", g.acc_plain, section))
    # A gate can look accurate by acting mostly on the easy class, so its reach per class.
    names = {REST: "REST", AH: "AH", SF: "SF"}
    for arm in CONFIG["arms"]:
        g = gate[gate.arm == arm].groupby("subject").mean(numeric_only=True)
        for c_ in CONFIG["tasks"][CONFIG["arms"][arm]["task"]]:
            table.append(describe(f"{arm}, share of {names[c_]} windows acted on",
                                  g[f"share_acted_label{c_}"], "gate_share_by_class",
                                  headline=arm == headline))  # fmt: skip
    pd.DataFrame(table).to_csv(out("table.csv"), index=False, float_format="%.6g")

    paired = []
    for arm in PART1:
        if CONFIG["arms"][arm]["role"] == "baseline":
            continue
        for base in ("csp_lda", "ts_lr", "ts_lr_c14"):
            paired.append(compare(f"{arm} vs {base}", test_pp[arm], test_pp[base], arm, base))
    paired.append(compare("ts_lr_c14 vs ts_lr", test_pp.ts_lr_c14, test_pp.ts_lr, "ts_lr_c14",
                          "ts_lr"))  # fmt: skip
    paired.append(compare(f"R ({headline}) acting vs {headline} all windows", gp.acc_w,
                          test_pp[headline], "accuracy when acting",
                          "balanced accuracy, all windows"))  # fmt: skip
    f = fires_p.loc[headline]
    for gated in ("", "_gated"):
        ah, rest, sf = f[f"fire_ah{gated}"], f[f"fire_rest{gated}"], f[f"fire_sf{gated}"]
        paired.append(compare(f"{headline} fires on AH vs on REST{gated}", ah, rest,
                              "AH fire rate", "REST fire rate"))  # fmt: skip
        paired.append(compare(f"{headline} fires on SF vs on AH{gated}", sf, ah,
                              "SF fire rate", "AH fire rate"))  # fmt: skip
    for t in ("T1", "T2"):
        paired.append(compare(f"{t}_ea_ft vs {t}_ts_lr, all windows", test_pp[f"{t}_ea_ft"],
                              test_pp[f"{t}_ts_lr"], f"{t}_ea_ft", f"{t}_ts_lr"))  # fmt: skip
        paired.append(compare(f"{t}_ea_ft vs {t}_ts_lr, accuracy when acting",
                              gate_p.loc[f"{t}_ea_ft"].acc_w, gate_p.loc[f"{t}_ts_lr"].acc_w,
                              f"{t}_ea_ft", f"{t}_ts_lr"))  # fmt: skip
    pd.DataFrame(paired).to_csv(out("paired.csv"), index=False, float_format="%.6g")

    cov = []
    for (arm, share), g in cover_p.groupby(level=["arm", "share"]):
        m, lo, hi = bootstrap_ci(g.acc_w.dropna().to_numpy())
        cov.append(dict(task=CONFIG["arms"][arm]["task"], arm=arm, share=share, n=len(g),
                        acc_when_acting=m, ci_lo=lo, ci_hi=hi,
                        plain_acc_when_acting=float(g.acc_plain.mean()),
                        headline=arm == headline))  # fmt: skip
    for arm in CONFIG["arms"]:
        g = gate_p.loc[arm]
        cov.append(dict(task=CONFIG["arms"][arm]["task"], arm=arm, share="gate (arm R rule)",
                        n=int(g.acc_w.notna().sum()), acc_when_acting=float(g.acc_w.mean()),
                        ci_lo=np.nan, ci_hi=np.nan,
                        plain_acc_when_acting=float(g.acc_plain.mean()),
                        mean_share_acted=float(g.share.mean()),
                        headline=arm == headline))  # fmt: skip
    pd.DataFrame(cov).to_csv(out("coverage.csv"), index=False, float_format="%.6g")

    pp = test_pp[list(CONFIG["arms"])].add_prefix("test_")
    pp = pp.join(pd.read_csv(out("selection_per_patient.csv")).set_index("subject")
                 [list(CONFIG["arms"])].add_prefix("inner_"))  # fmt: skip
    pp = pp.join(gp[["threshold", "acc_w", "acc_plain", "share"]].add_prefix("R_"))
    for arm in PART1:
        pp[f"fire_ah_{arm}"] = fires_p.loc[arm].fire_ah
    for col in ("fire_rest", "fire_sf", "fire_ah_gated", "fire_rest_gated", "fire_sf_gated"):
        pp[f"{col}_{headline}"] = fires_p.loc[headline][col]
    for arm in ("T1_ts_lr", "T1_ea_ft", "T2_ts_lr", "T2_ea_ft"):
        pp = pp.join(gate_p.loc[arm][["acc_w", "share"]].add_prefix(f"{arm}_acting_"))
    pp.rename_axis("subject").reset_index().to_csv(out("per_patient.csv"), index=False,
                                                    float_format="%.4g")  # fmt: skip
    gate.to_csv(out("gate_per_seed.csv"), index=False, float_format="%.6g")
    fits(inner, test).to_csv(out("fits.csv"), index=False, float_format="%.6g")
    out("checks.json").write_text(json.dumps(checks, indent=2) + "\n")
    for k, v in checks.items():
        log.info("check: %s = %s", k, v)
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        log.info("\n%s", pd.DataFrame(table).round(4).to_string(index=False))
        cols = ["comparison", "arm_mean", "base_mean", "diff_points", "diff_ci_lo", "diff_ci_hi",
                "p_wilcoxon", "better", "worse", "diff_points_without_dev"]  # fmt: skip
        log.info("\n%s", pd.DataFrame(paired)[cols].round(4).to_string(index=False))


def fits(inner: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    """Every fit's balanced accuracy, with where its predictions came from."""
    parts = []
    for pred in (inner, test):
        fs = fold_scores(pred)
        prov = pred.groupby(["arm", "seed", "fold", "subject"])[
            [c for c in ("git_sha", "source_commit") if c in pred]
        ].first()
        parts.append(fs.join(prov, on=["arm", "seed", "fold", "subject"]))
    return pd.concat(parts, ignore_index=True)


def part_carry(research: Path) -> None:
    """The EEGNet parts' predictions as the exploratory run made them, with the commit."""
    for fold_set in ("inner", "test"):
        name = f"pred_{fold_set}_eegnet.csv"
        df = ex.carry(research / name, pred_path(fold_set, "eegnet"), PRED_COLUMNS)
        log.info("carried %s: %d rows, committed in %s", name, len(df), df.source_commit.iloc[0])


def part_repro(research: Path) -> None:
    names = ["selection.csv", "selection_per_patient.csv", "thresholds.csv", "table.csv",
             "paired.csv", "coverage.csv", "per_patient.csv", "gate_per_seed.csv",
             "checks.json"]  # fmt: skip
    parts = [ex.repro_table(NAME, research, {n: out(n) for n in names})]
    preds = {f"pred_{f}_{k}.csv": pred_path(f, k) for f in ("inner", "test")
             for k in ("classical", "eegnet")}  # fmt: skip
    # Fit times are the machine's, not a result.
    parts.append(ex.repro_table(NAME, research, preds, ("git_sha", "source_commit", "fit_seconds")))
    for path in sorted(RUNS_DIR.glob("rerun_pred_*.csv")):
        new = pd.read_csv(path)
        old = pd.read_csv(RUNS_DIR / path.name.removeprefix("rerun_"))
        old = old[old.subject.isin(new.subject)].reset_index(drop=True)
        res = ex.table_diff(new.drop(columns="fit_seconds"), old.drop(columns="fit_seconds"))
        note = "re-run here for " + " ".join(new.subject.unique()) + "; fit times not compared"
        parts.append(pd.DataFrame([dict(analysis=NAME, file=f"rerun of {path.name[6:]}",
                                        before=path.name[6:], **res, note=note)]))  # fmt: skip
    before = json.loads((research / "config.json").read_text())
    parts.append(pd.DataFrame([dict(analysis=NAME, **ex.settings_diff(CONFIG, before))]))
    table = pd.concat(parts, ignore_index=True)
    table["git_sha"] = current_git_sha()
    table.to_csv(out("repro.csv"), index=False, float_format="%.6g")
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        log.info("\n%s", table.drop(columns="note").to_string(index=False))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parts = ["inner_classical", "inner_eegnet", "select", "test_classical", "test_eegnet",
             "summary", "carry", "repro"]  # fmt: skip
    ap.add_argument("--part", required=True, choices=parts)
    ap.add_argument("--subjects", nargs="+", default=None, help="re-run these patients only")
    ap.add_argument("--research", type=Path, help="carry, repro: folder of the exploratory run")
    args = ap.parse_args()
    if args.part in ("carry", "repro") and args.research is None:
        ap.error("--research is needed for carry and repro")
    setup_logging()
    a = ex.settings("ex1_transfer_ah_sf")["arm_A"]
    w = CONFIG["arm_W"]
    if (a["crop_starts_s"], a["crop_length_s"]) != (w["crop_starts_s"], w["crop_length_s"]):
        raise SystemExit("arm W's crops differ from ex1_transfer_ah_sf arm A's")
    t0, c0 = time.perf_counter(), time.process_time()
    log.info("part %s start, git %s", args.part, current_git_sha())
    if args.part in ("test_classical", "test_eegnet"):
        require_headline()
    {
        "inner_classical": lambda: run_part("inner", "classical", classical_patient, args.subjects),
        "inner_eegnet": lambda: run_part("inner", "eegnet", eegnet_patient, args.subjects),
        "select": part_select,
        "test_classical": lambda: run_part("test", "classical", classical_patient, args.subjects),
        "test_eegnet": lambda: run_part("test", "eegnet", eegnet_patient, args.subjects),
        "summary": part_summary,
        "carry": lambda: part_carry(args.research),
        "repro": lambda: part_repro(args.research),
    }[args.part]()
    log.info("part %s done: %.0f s wall, %.0f s CPU (this process)", args.part,
             time.perf_counter() - t0, time.process_time() - c0)  # fmt: skip


if __name__ == "__main__":
    main()
