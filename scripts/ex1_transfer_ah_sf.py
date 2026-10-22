"""Exploratory, added after the results: more data per decision for AH vs SF (T1_ah_vs_sf).

uv run python scripts/ex1_transfer_ah_sf.py --part A          # cropped training, ts_lr
uv run python scripts/ex1_transfer_ah_sf.py --part C          # pooled sessions, rct_tslr
uv run python scripts/ex1_transfer_ah_sf.py --part B          # pre-trained EEGNet, fine-tuned
uv run python scripts/ex1_transfer_ah_sf.py --part B_central  # only if B is the best arm
uv run python scripts/ex1_transfer_ah_sf.py --part summary

`pre`, learn runs 01-02, test runs 03-04 (only scored, never used to choose). Settings:
configs/experiments/ex1_transfer_ah_sf.yaml, fixed before any score. B and B_central fine-tune
EEGNet on the CPU (about 15 min together); `--part carry --research DIR` takes their per-fit
values from the exploratory run in DIR with the commit that holds them, `--part B --subjects
...` re-runs a few patients beside them, and `--part repro --research DIR` compares every
output with that run's. Writes results/summary/ex1_transfer_ah_sf_*.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import balanced_accuracy_score

import sixthfinger.models  # noqa: F401  (registers every method)
from sixthfinger.config import load_data_config
from sixthfinger.data.channels import CENTRAL_14
from sixthfinger.data.epochs import load_windows
from sixthfinger.evaluation import exploratory as ex
from sixthfinger.evaluation.leakage import LeakageError, assert_no_leakage
from sixthfinger.evaluation.metrics import score
from sixthfinger.evaluation.runner import method_params
from sixthfinger.models.registry import Batch, make_method
from sixthfinger.paths import current_git_sha, get_paths
from sixthfinger.preprocessing.alignment import align
from sixthfinger.preprocessing.covariance import CovarianceStore

NAME = "ex1_transfer_ah_sf"
CONFIG = ex.settings(NAME)
RUNS = get_paths().runs / NAME
VALUES = ["values_A.csv", "values_B.csv", "values_B_central.csv", "values_C.csv"]
EXPENSIVE = ["values_B.csv", "values_B_central.csv"]

log = logging.getLogger(NAME)


def out(name: str) -> Path:
    return get_paths().summary / f"{NAME}_{name}"


def setup_logging() -> None:
    RUNS.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S")
    for h in (logging.StreamHandler(), logging.FileHandler(RUNS / "run.log")):
        h.setFormatter(fmt)
        log.addHandler(h)
    log.setLevel(logging.INFO)


def session_windows(subject: str, session: str):
    paths, cfg = get_paths(), load_data_config()
    X, md = load_windows(paths.epochs, cfg, subjects=[subject], sessions=[session], labels=[1, 2])
    return X, md.reset_index(drop=True)


def split(md: pd.DataFrame):
    tr = md.index[md.run.isin(CONFIG["train_runs"])].to_numpy()
    te = md.index[md.run.isin(CONFIG["test_runs"])].to_numpy()
    assert_no_leakage(md.iloc[tr], md.iloc[te])
    return tr, te


def ts_lr(X, y, md):
    m = make_method("ts_lr", n_classes=2, **method_params("ts_lr", get_paths().configs))
    return m.fit(Batch(X, y, md))


def bal(y, proba) -> float:
    return score(y, proba, CONFIG["classes"])["bal_acc"]


def channel_sets() -> dict[str, list[int] | None]:
    return {"all_40": None, "central_14": ex.channel_index(load_data_config(), CENTRAL_14)}


def pre_subjects() -> list[str]:
    return ex.pre_subjects(load_data_config())


def save(rows: list[dict], path: Path) -> None:
    df = pd.DataFrame(rows)
    df["git_sha"] = current_git_sha()
    df.to_csv(path, index=False, float_format="%.6g")
    log.info("wrote %s (%d rows)", path.name, len(df))


def part_a() -> None:
    a = CONFIG["arm_A"]
    paths, cfg = get_paths(), load_data_config()
    rows = []
    for subject in pre_subjects():
        t0 = time.perf_counter()
        X, md = session_windows(subject, "pre")
        tr, te = split(md)
        y = md.label.to_numpy()
        crops = ex.crops_for(subject, X, md, cfg, paths.processed, a["crop_starts_s"],
                             a["crop_length_s"])  # fmt: skip
        n_drop = {s: int(len(md) - len(r)) for s, (r, _) in crops.items()}
        for set_name, chans in channel_sets().items():
            Xb = X if chans is None else X[:, chans]
            base = ts_lr(Xb[tr], y[tr], md.iloc[tr])
            parts_X, parts_md = [], []
            for kept, Xs in crops.values():
                sel = kept[np.isin(kept, tr)]
                Xc = Xs[np.isin(kept, tr)]
                parts_X.append(Xc if chans is None else Xc[:, chans])
                parts_md.append(md.iloc[sel])
            md_crop = pd.concat(parts_md)
            assert_no_leakage(md_crop, md.iloc[te])
            if not md_crop.run.isin(CONFIG["train_runs"]).all():
                raise LeakageError("a training crop outside runs 01-02")
            cropped = ts_lr(np.concatenate(parts_X), md_crop.label.to_numpy(), md_crop)
            values = {
                "baseline_standard": bal(y[te], base.predict_proba(Xb[te])),
                "crops_standard": bal(y[te], cropped.predict_proba(Xb[te])),
                "crops_crop_mean": bal(y[te], ex.crop_mean(cropped, crops, te, len(md), chans)),
                "baseline_crop_mean": bal(y[te], ex.crop_mean(base, crops, te, len(md), chans)),
            }
            for row, v in values.items():
                rows.append(dict(arm="A", subject=subject, session="pre", channels=set_name,
                                 row=row, bal_acc=v, n_train=len(tr), n_test=len(te),
                                 n_train_crops=len(md_crop),
                                 dropped_per_start=json.dumps(n_drop)))  # fmt: skip
        log.info("A %s: %.1f s, dropped crops %s", subject, time.perf_counter() - t0, n_drop)
        del X, crops
    save(rows, out("values_A.csv"))


def part_c() -> None:
    cfg, paths = load_data_config(), get_paths()
    rct_params = method_params("rct_tslr", paths.configs)
    rows = []
    for subject in [s for s in pre_subjects() if "post" in cfg.sessions_for(s)]:
        t0 = time.perf_counter()
        X_pre, md_pre = session_windows(subject, "pre")
        X_post, md_post = session_windows(subject, "post")
        tr, te = split(md_post)
        y_pre, y_post = md_pre.label.to_numpy(), md_post.label.to_numpy()
        for set_name, chans in channel_sets().items():
            Xp = X_pre if chans is None else X_pre[:, chans]
            Xq = X_post if chans is None else X_post[:, chans]
            train_md = md_post.iloc[tr]
            assert_no_leakage(train_md, md_post.iloc[te], source=md_pre, unlabelled=train_md)
            base = ts_lr(Xq[tr], y_post[tr], train_md)
            store = CovarianceStore(Xp, md_pre, rct_params["covariance"])
            rct = make_method("rct_tslr", n_classes=2, **rct_params).fit(
                Batch(Xq[tr], y_post[tr], train_md),
                Batch(None, y_pre, md_pre, store=store),
                Batch(Xq[tr], None, train_md),
            )
            md_pool = pd.concat([md_pre, train_md])
            plain = ts_lr(np.concatenate([Xp, Xq[tr]]), md_pool.label.to_numpy(), md_pool)
            values = {
                "post_only": bal(y_post[te], base.predict_proba(Xq[te])),
                "rct_pooled": bal(y_post[te], rct.predict_proba(Xq[te])),
                "plain_pooled": bal(y_post[te], plain.predict_proba(Xq[te])),
            }
            for row, v in values.items():
                rows.append(dict(arm="C", subject=subject, session="post", channels=set_name,
                                 row=row, bal_acc=v, n_train_post=len(tr), n_pre=len(md_pre),
                                 n_test=len(te)))  # fmt: skip
        log.info("C %s: %.1f s", subject, time.perf_counter() - t0)
    save(rows, out("values_C.csv"))


def ea_ft():
    paths = get_paths()
    params = method_params("eegnet_ea_ft", paths.configs) | {"device": CONFIG["arm_B"]["device"]}
    return make_method(
        "eegnet_ea_ft", n_classes=2, classes=CONFIG["classes"],
        models_dir=paths.models / "pretrained", mirror=False, **params,
    )  # fmt: skip


def committed_style(m, X: np.ndarray, y: np.ndarray) -> float:
    """P07's zero-shot T1 value: argmax of the AH and SF columns before renormalising."""
    p = m.clf.predict_proba(m._x(align(X, m.R)))[:, CONFIG["classes"]]
    pred = np.asarray(CONFIG["classes"])[p.argmax(axis=1)]
    return float(balanced_accuracy_score(y, pred))


def part_b(central: bool, subjects: list[str] | None) -> None:
    """Arm B, or its central control; with `subjects`, a re-run of those beside the values."""
    b = CONFIG["arm_B"]
    torch.set_num_threads(b["torch_threads"])
    paths, cfg = get_paths(), load_data_config()
    others = None
    if central:
        best = best_arm()
        if best != "B":
            raise SystemExit(f"best arm is {best}, not B: the B central control is not run")
        others = [i for i in range(40) if i not in channel_sets()["central_14"]]
    zs = pd.read_csv(paths.summary / "dl_zeroshot_subject_values.csv")
    zs = zs[zs.task == "T1_ah_vs_sf"].set_index("subject").bal_acc
    name = "values_B_central.csv" if central else "values_B.csv"
    partial = RUNS / f"{name}.partial"
    rows = pd.read_csv(partial).to_dict("records") if partial.exists() and not subjects else []
    done = {r["subject"] for r in rows}
    tag = "central_14_zeroed" if central else "all_40"
    for subject in subjects or pre_subjects():
        if subject in done:
            continue
        t0 = time.perf_counter()
        X, md = session_windows(subject, "pre")
        if others is not None:
            X = X.copy()
            X[:, others] = 0.0
        tr, te = split(md)
        y = md.label.to_numpy()
        train_md = md.iloc[tr]
        assert_no_leakage(train_md, md.iloc[te], unlabelled=train_md)
        new = []
        for seed in b["seeds"]:
            m = ea_ft().fit(Batch(X[tr], y[tr], train_md), unlabelled=Batch(X[tr], None, train_md),
                            seed=seed)  # fmt: skip
            if others is not None:
                leak = np.abs(align(X[tr], m.R)[:, others]).max()
                kept = np.abs(align(X[tr], m.R)).max()
                if leak > 1e-6 * kept:
                    raise AssertionError(f"{subject}: alignment moved signal into zeroed channels")
            proba, n_nan = ex.task_proba(m, X[te], CONFIG["classes"])
            new.append(dict(arm="B", subject=subject, session="pre", channels=tag,
                            row="finetuned", seed=seed, bal_acc=bal(y[te], proba),
                            n_registry_nan=n_nan, n_train=len(tr), n_test=len(te)))  # fmt: skip
        m0 = ea_ft().fit(Batch(None, None, train_md.iloc[:0]),
                         unlabelled=Batch(X[tr], None, train_md))  # fmt: skip
        proba, n_nan = ex.task_proba(m0, X[te], CONFIG["classes"])
        new.append(dict(arm="B", subject=subject, session="pre", channels=tag,
                        row="pretrained_same_alignment", seed=-1, bal_acc=bal(y[te], proba),
                        n_registry_nan=n_nan, n_train=0, n_test=len(te)))  # fmt: skip
        if not central:
            # Loading check: P07's zero-shot, aligned on the REST windows of runs 01-02.
            Xr, mdr = load_windows(paths.epochs, cfg, subjects=[subject], sessions=["pre"],
                                   labels=[0])  # fmt: skip
            mdr = mdr.reset_index(drop=True)
            ref = mdr.index[mdr.run.isin(CONFIG["train_runs"])].to_numpy()
            mz = ea_ft().fit(Batch(None, None, mdr.iloc[:0]),
                             unlabelled=Batch(Xr[ref], None, mdr.iloc[ref]))  # fmt: skip
            proba, n_nan = ex.task_proba(mz, X[te], CONFIG["classes"])
            new.append(dict(arm="B", subject=subject, session="pre", channels=tag,
                            row="zeroshot_rest_alignment", seed=-1, bal_acc=bal(y[te], proba),
                            committed_style=committed_style(mz, X[te], y[te]),
                            committed=zs.get(subject, np.nan), n_registry_nan=n_nan,
                            n_train=0, n_test=len(te)))  # fmt: skip
        rows += new
        if not subjects:
            pd.DataFrame(rows).to_csv(partial, index=False)
        log.info("B%s %s: %.1f s, NaN windows of the method %s", " central" if central else "",
                 subject, time.perf_counter() - t0,
                 [r["n_registry_nan"] for r in new])  # fmt: skip
    if subjects:
        save(rows, RUNS / f"rerun_{name}")
        return
    save(rows, out(name))
    partial.unlink()


def series(df: pd.DataFrame, row: str, channels: str = "all_40") -> pd.Series:
    """One value per patient: the mean over seeds where there are several."""
    g = df[(df.row == row) & (df.channels == channels)]
    return g.groupby("subject").bal_acc.mean()


def comparisons() -> tuple[pd.DataFrame, dict]:
    c = ex.t1_baselines()
    compare = ex.paired_row
    checks = {}
    rows = []
    a = pd.read_csv(out("values_A.csv"))
    base_a = series(a, "baseline_standard")
    checks["A baseline vs committed P06 ts_lr chrono pre (max abs diff)"] = float(
        (base_a - c["ts_lr_pre"].reindex(base_a.index)).abs().max()
    )
    base_a_c = series(a, "baseline_standard", "central_14")
    checks["A central baseline vs committed rq4_visual_cue central_14 (max abs diff)"] = float(
        (base_a_c - c["ts_lr_pre_central"].reindex(base_a_c.index)).abs().max()
    )
    for ch in ("all_40", "central_14"):
        sfx = "" if ch == "all_40" else " [central_14]"
        base = series(a, "baseline_standard", ch)
        rows.append(compare(f"A_standard{sfx}", series(a, "crops_standard", ch), base,
                            "ts_lr cropped training, [1,5) test", "ts_lr [1,5)"))  # fmt: skip
        rows.append(compare(f"A_crop_mean{sfx}", series(a, "crops_crop_mean", ch), base,
                            "ts_lr cropped training, crop-mean test", "ts_lr [1,5)"))  # fmt: skip
        rows.append(compare(f"A_baseline_crop_mean{sfx}", series(a, "baseline_crop_mean", ch),
                            base, "ts_lr [1,5) training, crop-mean test",
                            "ts_lr [1,5)"))  # fmt: skip
    cc = pd.read_csv(out("values_C.csv"))
    base_c = series(cc, "post_only")
    checks["C baseline vs committed P06 ts_lr chrono post (max abs diff)"] = float(
        (base_c - c["ts_lr_post"].reindex(base_c.index)).abs().max()
    )
    for ch in ("all_40", "central_14"):
        sfx = "" if ch == "all_40" else " [central_14]"
        base = series(cc, "post_only", ch)
        rows.append(compare(f"C{sfx}", series(cc, "rct_pooled", ch), base,
                            "rct_tslr pre + post 01-02", "ts_lr post 01-02"))  # fmt: skip
        rows.append(compare(f"C_plain_pooled{sfx}", series(cc, "plain_pooled", ch), base,
                            "ts_lr pre + post 01-02, no re-centring",
                            "ts_lr post 01-02"))  # fmt: skip
    if out("values_B.csv").exists():
        b = pd.read_csv(out("values_B.csv"))
        ft = series(b, "finetuned")
        zr = b[b.row == "zeroshot_rest_alignment"].set_index("subject")
        key = "B zero-shot, committed-style argmax, vs committed dl_zeroshot T1 (max abs diff)"
        checks[key] = float((zr.committed_style - zr.committed).abs().max())
        checks["B zero-shot, log-space probabilities, vs committed (max abs diff)"] = float(
            (zr.bal_acc - zr.committed).abs().max()
        )
        checks["B zero-shot patients with registry NaN windows"] = float(
            (zr.n_registry_nan > 0).sum()
        )
        checks["B fine-tuned fits with registry NaN windows"] = float(
            (b[b.row == "finetuned"].n_registry_nan > 0).sum()
        )
        rows.append(compare("zeroshot_rest_logspace_vs_committed", zr.bal_acc, zr.committed,
                            "zero-shot, log-space", "zero-shot as committed"))  # fmt: skip
        seed_sd = b[b.row == "finetuned"].groupby("subject").bal_acc.std().mean()
        checks["B mean seed SD (points)"] = float(seed_sd * 100)
        pre_aligned = series(b, "pretrained_same_alignment")
        rows.append(compare("B", ft, c["eegnet_scratch_pre"], "eegnet_ea_ft k=all",
                            "eegnet_scratch"))  # fmt: skip
        rows.append(compare("B_vs_ts_lr", ft, c["ts_lr_pre"], "eegnet_ea_ft k=all", "ts_lr"))
        rows.append(compare("B_vs_zeroshot_rest", ft, c["zeroshot_rest_pre"],
                            "eegnet_ea_ft k=all", "zero-shot, REST alignment"))  # fmt: skip
        rows.append(compare("B_pretrained_same_alignment", pre_aligned, c["eegnet_scratch_pre"],
                            "pre-trained, no fine-tuning, AH+SF alignment",
                            "eegnet_scratch"))  # fmt: skip
        rows.append(compare("B_vs_pretrained_same_alignment", ft, pre_aligned,
                            "eegnet_ea_ft k=all",
                            "pre-trained, no fine-tuning, AH+SF alignment"))  # fmt: skip
        rows.append(compare("B_pretrained_same_alignment_vs_ts_lr", pre_aligned, c["ts_lr_pre"],
                            "pre-trained, no fine-tuning, AH+SF alignment", "ts_lr"))  # fmt: skip
    if out("values_B_central.csv").exists():
        bc = pd.read_csv(out("values_B_central.csv"))
        rows.append(compare("B_vs_ts_lr [central_14]", series(bc, "finetuned", "central_14_zeroed"),
                            c["ts_lr_pre_central"], "eegnet_ea_ft k=all, central only",
                            "ts_lr central"))  # fmt: skip
        rows.append(compare("B_pretrained_same_alignment_vs_ts_lr [central_14]",
                            series(bc, "pretrained_same_alignment", "central_14_zeroed"),
                            c["ts_lr_pre_central"], "pre-trained, no fine-tuning, central only",
                            "ts_lr central"))  # fmt: skip
        seed_sd = bc[bc.row == "finetuned"].groupby("subject").bal_acc.std().mean()
        checks["B central mean seed SD (points)"] = float(seed_sd * 100)
    return pd.DataFrame(rows), checks


def best_arm() -> str:
    """The fixed rule: the largest mean gain over its own primary baseline."""
    table, _ = comparisons()
    primary = table[table.comparison.isin(["A_standard", "A_crop_mean", "B", "C"])]
    if "B" not in set(primary.comparison):
        raise SystemExit("arm B has not been run yet; the best arm cannot be decided")
    return str(primary.loc[primary.diff_points.idxmax(), "comparison"])


def per_patient() -> pd.DataFrame:
    """Every primary arm next to its baseline, all 40 channels."""
    c = ex.t1_baselines()
    a = pd.read_csv(out("values_A.csv"))
    cc = pd.read_csv(out("values_C.csv"))
    cols = {
        "A_base_ts_lr_pre": series(a, "baseline_standard"),
        "A_crops_standard": series(a, "crops_standard"),
        "A_crops_crop_mean": series(a, "crops_crop_mean"),
        "C_base_ts_lr_post": series(cc, "post_only"),
        "C_rct_pooled": series(cc, "rct_pooled"),
    }
    if out("values_B.csv").exists():
        b = pd.read_csv(out("values_B.csv"))
        cols |= {
            "B_base_eegnet_scratch_pre": c["eegnet_scratch_pre"],
            "B_finetuned_seed_mean": series(b, "finetuned"),
            "B_pretrained_same_alignment": series(b, "pretrained_same_alignment"),
        }
    return pd.DataFrame(cols).rename_axis("subject").reset_index()


def part_summary() -> None:
    table, checks = comparisons()
    table.to_csv(out("paired.csv"), index=False, float_format="%.6g")
    per_patient().to_csv(out("per_patient.csv"), index=False, float_format="%.4g")
    out("checks.json").write_text(json.dumps(checks, indent=2) + "\n")
    for k, v in checks.items():
        log.info("check: %s = %.3g", k, v)
    cols = ["comparison", "n", "arm_mean", "base_mean", "diff_points", "diff_ci_lo",
            "diff_ci_hi", "p_wilcoxon", "better", "worse", "tied",
            "diff_points_without_dev", "diff_ci_lo_without_dev",
            "diff_ci_hi_without_dev"]  # fmt: skip
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        log.info("\n%s", table[cols].round(4).to_string(index=False))
    primary = table[table.comparison.isin(["A_standard", "A_crop_mean", "B", "C"])]
    if len(primary) == 4:
        log.info("best arm by the fixed rule: %s", best_arm())


def part_carry(research: Path) -> None:
    """B and B_central as the exploratory run computed them, with the commit that holds them."""
    base = ["arm", "subject", "session", "channels", "row", "seed", "bal_acc", "n_registry_nan",
            "n_train", "n_test"]  # fmt: skip
    columns = {"values_B.csv": [*base, "committed_style", "committed", "git_sha"],
               "values_B_central.csv": [*base, "git_sha"]}  # fmt: skip
    for name in EXPENSIVE:
        df = ex.carry(research / name, out(name), columns[name])
        log.info("carried %s: %d rows, run at %s, committed in %s", name, len(df),
                 sorted(df.git_sha.unique()), df.source_commit.iloc[0])  # fmt: skip


def part_repro(research: Path) -> None:
    names = [*VALUES, "paired.csv", "per_patient.csv", "checks.json"]
    table = ex.repro_table(NAME, research, {n: out(n) for n in names})
    rows = [table]
    for name in EXPENSIVE:
        rerun = RUNS / f"rerun_{name}"
        if not rerun.exists():
            continue
        new = pd.read_csv(rerun)
        old = pd.read_csv(out(name))
        old = old[old.subject.isin(new.subject)].reset_index(drop=True)
        res = ex.table_diff(new, old[[c for c in old.columns if c in new.columns]])
        note = "re-run here for " + " ".join(new.subject.unique())
        rows.append(pd.DataFrame([dict(analysis=NAME, file=f"rerun of {name}",
                                       before=f"{NAME}_{name}", **res, note=note)]))  # fmt: skip
    before = json.loads((research / "config.json").read_text())
    rows.append(pd.DataFrame([dict(analysis=NAME, **ex.settings_diff(CONFIG, before))]))
    table = pd.concat(rows, ignore_index=True)
    table["git_sha"] = current_git_sha()
    table.to_csv(out("repro.csv"), index=False, float_format="%.6g")
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        log.info("\n%s", table.drop(columns="note").to_string(index=False))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--part", required=True,
                    choices=["A", "B", "C", "B_central", "summary", "carry", "repro"])  # fmt: skip
    ap.add_argument("--subjects", nargs="+", default=None, help="B or B_central: re-run these")
    ap.add_argument("--research", type=Path, help="carry, repro: folder of the exploratory run")
    args = ap.parse_args()
    if args.part in ("carry", "repro") and args.research is None:
        ap.error("--research is needed for carry and repro")
    setup_logging()
    t0, c0 = time.perf_counter(), time.process_time()
    log.info("part %s start, git %s", args.part, current_git_sha())
    {
        "A": part_a,
        "B": lambda: part_b(central=False, subjects=args.subjects),
        "C": part_c,
        "B_central": lambda: part_b(central=True, subjects=args.subjects),
        "summary": part_summary,
        "carry": lambda: part_carry(args.research),
        "repro": lambda: part_repro(args.research),
    }[args.part]()
    log.info("part %s done: %.0f s wall, %.0f s CPU (this process)", args.part,
             time.perf_counter() - t0, time.process_time() - c0)  # fmt: skip


if __name__ == "__main__":
    main()
