"""RQ1b: the four within-session protocols with csp_lda on public motor-imagery datasets.

Protocol 4.1b and pre-registration 3.3. Left vs right hand imagery through MOABB, every
subject of the dataset, the same splits, leakage guard and replica as on our data.

uv run --extra moabb python scripts/rq1b_public.py --check-disk
uv run --extra moabb python scripts/rq1b_public.py --datasets BNCI2014_001 --subjects 1 2
uv run --extra moabb python scripts/rq1b_public.py --datasets BNCI2014_001
uv run --extra moabb python scripts/rq1b_public.py --summarise-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from sixthfinger.config import load_protocol_config
from sixthfinger.evaluation.runner import (
    ScoreWriter,
    completed_units,
    method_params,
    score_folds,
    unit_key,
    within_splits,
)
from sixthfinger.evaluation.splits import chrono_split
from sixthfinger.evaluation.summary import (
    WITHIN_PROTOCOLS,
    describe,
    h1b_category,
    holm_family,
    paired,
    subject_values,
)
from sixthfinger.paths import current_git_sha, get_paths

log = logging.getLogger("rq1b")

DATASETS = ["BNCI2014_001", "Cho2017"]  # the pre-registered pair, in download order
PARADIGM = {"fmin": 5, "fmax": 35, "resample": 250}
METHOD = "csp_lda"
TASK = "left_vs_right"
CLASS_IDS = {"left_hand": 1, "right_hand": 2}
MIN_RUNS = 4
GB = 1e9


def _use_data_dir(paths) -> Path:
    """Keep MOABB downloads in the ignored data folder and out of the user's MNE config."""
    root = paths.data / "moabb"
    root.mkdir(parents=True, exist_ok=True)
    for key in ("MNE_DATA", "MNE_DATASETS_BNCI_PATH", "MNE_DATASETS_GIGADB_PATH"):
        os.environ[key] = str(root)
    return root


def _dataset(code: str):
    import moabb.datasets

    return getattr(moabb.datasets, code)()


def _file_urls(code: str, subjects: list[int]) -> list[str]:
    # The same URLs MOABB 1.7.2 fetches (bnci/bnci_2014.py, gigadb.py); listed here because
    # MOABB can only tell a file's location by downloading it.
    if code == "BNCI2014_001":
        from moabb.datasets.bnci.utils import BNCI_URL

        return [f"{BNCI_URL}001-2014/A{s:02d}{r}.mat" for s in subjects for r in "TE"]
    if code == "Cho2017":
        from moabb.datasets.gigadb import GIGA_URL

        return [f"{GIGA_URL}s{s:02d}.mat" for s in subjects]
    raise ValueError(f"No file list for {code}")


def download_sizes(codes: list[str], data_dir: Path, keep_free_gb: float) -> pd.DataFrame:
    """Bytes each dataset still has to download (HTTP Content-Length), against free disk."""
    import requests

    present = {p.name: p.stat().st_size for p in data_dir.rglob("*.mat")}
    free = shutil.disk_usage(data_dir).free
    rows, needed = [], 0
    for code in codes:
        urls = _file_urls(code, list(_dataset(code).subject_list))
        sizes = []
        for url in urls:
            head = requests.head(url, allow_redirects=True, timeout=60)
            head.raise_for_status()
            sizes.append(int(head.headers["Content-Length"]))
        have = sum(present.get(u.rsplit("/", 1)[-1], 0) for u in urls)
        missing = sum(sizes) - have
        needed += missing
        rows.append(
            dict(
                dataset=code,
                n_files=len(urls),
                download_gb=round(sum(sizes) / GB, 3),
                on_disk_gb=round(have / GB, 3),
                free_gb_now=round(free / GB, 3),
                free_gb_after_this=round((free - missing) / GB, 3),
                free_gb_after_all_listed=round((free - needed) / GB, 3),
                keep_free_gb=keep_free_gb,
                fits_with_margin=(free - missing) / GB >= keep_free_gb,
                checked_at=datetime.now(UTC).isoformat(timespec="seconds"),
            )
        )
    return pd.DataFrame(rows)


def session_metadata(meta: pd.DataFrame, code: str) -> tuple[pd.DataFrame, str]:
    """Trials of one session in recording order, with the run (or block) each belongs to.

    A session with fewer than four runs is cut into four blocks of consecutive trials,
    which play the role of runs (protocol 4.1b).
    """
    meta = meta.reset_index(drop=True)
    runs = list(dict.fromkeys(meta.run))
    if len(runs) >= MIN_RUNS:
        run = meta.run.map({r: i + 1 for i, r in enumerate(runs)}).to_numpy()
        source = "run"
    else:
        run = np.empty(len(meta), int)
        for i, block in enumerate(np.array_split(np.arange(len(meta)), MIN_RUNS)):
            run[block] = i + 1
        source = "blocks"
    subject, session = meta.subject.iloc[0], meta.session.iloc[0]
    md = pd.DataFrame(
        {
            "subject": f"sub-{int(subject):02d}",
            "session": str(session),
            "run": run,
            "trial_uid": [f"{code}_sub-{int(subject):02d}_{session}_{i:04d}" for i in meta.index],
        }
    )
    return md, source


def protocol_splits(name: str, md: pd.DataFrame, proto) -> tuple[list, int]:
    if name != "chrono":
        return within_splits(name, md, proto)
    # The first half of the runs (or blocks) trains, the second half tests.
    runs = sorted(md.run.unique())
    half = len(runs) // 2
    return [chrono_split(md, [str(r) for r in runs[:half]], [str(r) for r in runs[half:]])], 1


def run_dataset(code: str, subjects: list[int] | None, out_root: Path) -> Path:
    import moabb
    from moabb.paradigms import LeftRightImagery

    paths = get_paths()
    proto = load_protocol_config()
    params = method_params(METHOD, paths.configs)
    seed = proto.calibration.seed_base
    dataset = _dataset(code)
    paradigm = LeftRightImagery(**PARADIGM)
    subjects = subjects or list(dataset.subject_list)
    out = out_root / code / "scores.parquet"
    writer, done = ScoreWriter(out), completed_units(out)
    settings = dict(
        dataset=code,
        paradigm=PARADIGM,
        interval=list(dataset.interval),
        protocol=proto.within_session.model_dump(),
        seed=seed,
        params=params,
    )
    provenance = dict(
        git_sha=current_git_sha(),
        config_hash=hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:16],
        data_manifest_sha=f"moabb-{moabb.__version__}",
        dataset=code,
        interval=json.dumps(list(dataset.interval)),
    )
    classes = sorted(CLASS_IDS.values())
    try:
        for subject in subjects:
            X, labels, meta = paradigm.get_data(dataset, subjects=[subject])
            y_all = np.array([CLASS_IDS[label] for label in labels], np.int64)
            n_new = 0
            for _, idx in meta.groupby("session", sort=True).indices.items():
                md, source = session_metadata(meta.iloc[idx], code)
                md["label"] = y_all[idx]
                Xs = X[idx].astype(np.float32)
                for name in WITHIN_PROTOCOLS:
                    splits, n_folds = protocol_splits(name, md, proto)
                    key = dict(
                        experiment="rq1b_public",
                        protocol=name,
                        scenario=None,
                        task=TASK,
                        method=METHOD,
                        feature="bandpower",
                        subject=md.subject.iloc[0],
                        session=md.session.iloc[0],
                        k=None,
                        draw=None,
                    )
                    todo = [
                        (fold, split)
                        for fold, split in enumerate(splits)
                        if unit_key({**key, "fold": fold}) not in done
                    ]
                    for fold, metrics, extra in score_folds(
                        Xs, md.label.to_numpy(), md, todo, METHOD, params, classes, name, seed
                    ):
                        # The task has no sixth-finger class; the SF columns stay empty.
                        metrics.update(sf_recall=np.nan, sf_precision=np.nan, auc_sf=np.nan)
                        writer.append(
                            {
                                **key,
                                "fold": fold,
                                **metrics,
                                **extra,
                                "n_folds": n_folds,
                                "run_source": source,
                                "n_runs": int(md.run.nunique()),
                                "n_channels": Xs.shape[1],
                                "reason": None,
                                **provenance,
                                "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
                            }
                        )
                        n_new += 1
            writer.flush()
            log.info("%s sub-%02d: %d new rows", code, subject, n_new)
    finally:
        writer.flush()
    return out


def _our_dataset_h1(summary: Path) -> pd.DataFrame:
    path = summary / "rq1_stats.csv"
    if not path.exists():
        log.warning("%s not found; the table will lack our dataset's H1 row", path)
        return pd.DataFrame()
    stats = pd.read_csv(path)
    row = stats[stats.test_id == "H1"].copy()
    return row.assign(dataset="Wang2026 stroke (this study, T1, pre)", role="reference")


def summarise(out_root: Path, summary: Path, figures: Path) -> None:
    frames = [
        pd.read_parquet(p) for c in DATASETS if (p := out_root / c / "scores.parquet").exists()
    ]
    if not frames:
        raise SystemExit(f"No RQ1b scores under {out_root}")
    scores = pd.concat(frames, ignore_index=True)
    per_session = subject_values(scores, ["dataset", "protocol", "subject", "session"], 2)
    per_subject = per_session.groupby(["dataset", "protocol", "subject"], as_index=False)[
        "bal_acc"
    ].mean()
    summary.mkdir(parents=True, exist_ok=True)
    per_session.to_csv(summary / "rq1b_subject_values.csv", index=False)

    table = []
    for (code, name), rows in per_subject.groupby(["dataset", "protocol"], sort=False):
        sess = per_session[(per_session.dataset == code) & (per_session.protocol == name)]
        table.append(
            dict(
                dataset=code,
                protocol=name,
                **describe(rows.bal_acc),
                n_sessions=len(sess),
                n_sessions_above_chance=int(sess.above_chance.sum()),
                interval=scores[scores.dataset == code].interval.iloc[0],
                run_source=",".join(sorted(scores[scores.dataset == code].run_source.unique())),
            )
        )
    pd.DataFrame(table).to_csv(summary / "rq1b_table.csv", index=False, float_format="%.6g")

    wide = {
        code: rows.pivot_table(index="subject", columns="protocol", values="bal_acc")
        for code, rows in per_subject.groupby("dataset")
    }
    h1b = {
        code: (
            paired(wide[code], "paper_replica", "cv_leakfree", "greater") if code in wide else None
        )
        for code in DATASETS
    }
    p_adj = holm_family({c: (r["p"] if r else None) for c, r in h1b.items()})
    category = h1b_category(p_adj)
    stats = []
    for code, res in h1b.items():
        base = dict(test_id="H1b", dataset=code, role="confirmatory")
        comparison = "paper_replica - cv_leakfree"
        if res is None:
            stats.append(
                {**base, "comparison": comparison, "n": 0, "p_holm": p_adj[code], "note": "not run"}
            )
            continue
        stats.append({**base, "comparison": comparison, **res, "p_holm": p_adj[code]})
    for code, w in wide.items():
        desc = [
            ("cv_leakfree - loro", paired(w, "cv_leakfree", "loro")),
            ("loro - chrono", paired(w, "loro", "chrono")),
        ]
        adj = holm_family({c: r["p"] for c, r in desc})
        for comparison, res in desc:
            stats.append(
                dict(
                    test_id="descriptive",
                    dataset=code,
                    role="descriptive",
                    comparison=comparison,
                    **res,
                    p_holm=adj[comparison],
                )
            )
    stats = pd.DataFrame(stats)
    stats["h1b_category"] = np.where(stats.test_id == "H1b", category, "")
    stats = pd.concat([stats, _our_dataset_h1(summary)], ignore_index=True)
    stats.to_csv(summary / "rq1b_stats.csv", index=False, float_format="%.6g")
    log.info("H1b: %s (Holm-adjusted p %s)", category, p_adj)
    figure(per_subject, per_session, summary, figures)


def figure(per_subject: pd.DataFrame, per_session: pd.DataFrame, summary: Path, figures: Path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from sixthfinger.viz.plots import protocol_lines, save, use_style

    use_style()
    panels = []
    ours = summary / "rq1_subject_values.csv"
    if ours.exists():
        sv = pd.read_csv(ours)
        sv = sv[
            (sv.method == METHOD)
            & (sv.feature == "bandpower")
            & (sv.task == "T1_ah_vs_sf")
            & (sv.session == "pre")
        ]
        panels.append(("Stroke, AH vs SF (ours, pre)", sv))
    for code, rows in per_subject.groupby("dataset"):
        panels.append((f"{code}, left vs right", rows))
    fig, axes = plt.subplots(1, len(panels), figsize=(2.4 * len(panels), 2.8), sharey=True)
    axes = np.atleast_1d(axes)
    for ax, (title, rows) in zip(axes, panels, strict=True):
        wide = rows.pivot_table(index="subject", columns="protocol", values="bal_acc")
        ci = pd.DataFrame([describe(wide[p]) for p in WITHIN_PROTOCOLS], index=WITHIN_PROTOCOLS)
        protocol_lines(ax, wide, WITHIN_PROTOCOLS, title, chance=0.5, ci=ci)
    axes[0].set_ylabel("Balanced accuracy (CSP+LDA)")
    axes[0].set_ylim(0.2, 1.0)
    save(fig, figures, "rq1b_leakage_public")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--datasets", nargs="+", default=DATASETS, choices=DATASETS)
    ap.add_argument("--subjects", nargs="+", type=int, help="subset, for a first look")
    ap.add_argument("--check-disk", action="store_true", help="write download sizes and stop")
    ap.add_argument("--keep-free-gb", type=float, default=10.0, help="P06 disk rule margin")
    ap.add_argument(
        "--allow-low-disk",
        action="store_true",
        help="download although less than --keep-free-gb would stay free (still never more "
        "than the free space)",
    )
    ap.add_argument("--summarise-only", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")

    paths = get_paths()
    data_dir = _use_data_dir(paths)
    out_root = paths.runs / "rq1b_public"
    if args.check_disk:
        sizes = download_sizes(args.datasets, data_dir, args.keep_free_gb)
        paths.summary.mkdir(parents=True, exist_ok=True)
        sizes.to_csv(paths.summary / "rq1b_download_sizes.csv", index=False)
        print(sizes.to_string(index=False))
        return
    if not args.summarise_only:
        for code in args.datasets:
            check = download_sizes([code], data_dir, args.keep_free_gb).iloc[0]
            if check.free_gb_after_this < 0 or (
                not check.fits_with_margin and not args.allow_low_disk
            ):
                raise SystemExit(
                    f"{code}: {check.download_gb - check.on_disk_gb:.2f} GB to download, "
                    f"{check.free_gb_now:.2f} GB free; the disk rule keeps "
                    f"{args.keep_free_gb} GB free. Not downloading."
                )
            run_dataset(code, args.subjects, out_root)
    summarise(out_root, paths.summary, paths.figures)


if __name__ == "__main__":
    main()
