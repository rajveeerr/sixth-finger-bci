"""Choose the three open transfer values once for the whole study (P08 step 4.5).

uv run python scripts/select_transfer_hparams.py --methods rct_mdm rct_tslr
uv run python scripts/select_transfer_hparams.py --methods eegnet_ea_ft   # needs the P07 models

The pre-registered rule (pre-registration 3.6, DECISIONS 44, deviation log 2026-10-11):
pseudo-targets sub-01 and sub-03, session pre, S1, T2; the pool is run 01 and the score is
balanced accuracy on run 02, so no run 03 or 04 of either is read; k in {2, 5}; seeds 0-9
(EEGNet 0-4); sources as in the main study. The candidate with the highest mean balanced
accuracy over both subjects, both k and all draws wins. Ties: the smaller target weight; the
smaller learning rate, then the fewer epochs. Only sub-01 and sub-03 shape the values, so
the n = 20 sensitivity analysis is free of any selection.

Writes results/summary/transfer_hparams.csv (every candidate) and the winners into
configs/models/<method>.yaml.
"""

from __future__ import annotations

import argparse
import itertools
import logging
import re
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

from sixthfinger.evaluation.runner import method_params, run_experiment
from sixthfinger.paths import current_git_sha, get_paths

log = logging.getLogger("select")
PSEUDO_TARGETS = ["sub-01", "sub-03"]


def candidates(method: str, params: dict) -> list[dict]:
    """The method's grid, in tie-breaking order: earlier wins a tie."""
    if method.startswith("rct_"):
        return [{"target_weight": w} for w in sorted(params["target_weight_grid"])]
    grid = params["finetune_grid"]
    return [
        {"finetune_lr": lr, "finetune_epochs": ep}
        for lr, ep in itertools.product(sorted(grid["lr"]), sorted(grid["epochs"]))
    ]


def tag(candidate: dict) -> str:
    return "_".join(f"{k}{v:g}" for k, v in candidate.items()).replace(".", "p").replace("-", "m")


def run_candidate(method: str, candidate: dict, n_jobs: int, work: Path) -> pd.DataFrame:
    cfg = {
        "name": f"select_{method}_{tag(candidate)}",
        "protocol": "calibration",
        "tasks": ["T2_rest_ah_sf"],
        "sessions": ["pre"],
        "subjects": PSEUDO_TARGETS,
        "scenarios": ["S1_new_user"],
        "methods": [method],
        "k_grid": [2, 5],
        "pool_runs": ["01"],
        "test_runs": ["02"],
        "chrono_methods": [],  # the rule uses the random draws only
        "params": {method: candidate},
    }
    path = work / f"{cfg['name']}.yaml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=False))
    scores = pd.read_parquet(run_experiment(path, n_jobs=n_jobs))
    if scores.bal_acc.isna().any():
        raise RuntimeError(f"{cfg['name']}: missing scores: {scores.reason.dropna().unique()}")
    return scores


def summarise(method: str, cands: list[dict], scores: list[pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for order, (cand, s) in enumerate(zip(cands, scores, strict=True)):
        row = {"method": method, "tie_order": order, **cand, "n_rows": len(s)}
        row["mean_bal_acc"] = float(s.bal_acc.mean())
        for subject, g in s.groupby("subject"):
            row[f"mean_{subject}"] = float(g.bal_acc.mean())
        for k, g in s.groupby("k"):
            row[f"mean_k{int(k)}"] = float(g.bal_acc.mean())
        rows.append(row)
    table = pd.DataFrame(rows)
    # Highest mean wins; equal means go to the earlier candidate (the smaller value).
    best = table.sort_values(["mean_bal_acc", "tie_order"], ascending=[False, True]).index[0]
    table["chosen"] = table.index == best
    return table


def write_choice(config: Path, choice: dict, note: str) -> None:
    text = config.read_text()
    for key, value in choice.items():
        new, n = re.subn(rf"^{key}: null$", f"{key}: {value}  # {note}", text, flags=re.M)
        if n != 1:
            raise ValueError(f"{config}: expected one '{key}: null' line to fill in")
        text = new
    config.write_text(text)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--methods", nargs="+", required=True)
    ap.add_argument("--jobs", type=int, default=2)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    paths = get_paths()
    out = paths.results / "summary" / "transfer_hparams.csv"
    tables = [pd.read_csv(out)] if out.exists() else []
    tables = [t[~t.method.isin(args.methods)] for t in tables]
    with tempfile.TemporaryDirectory() as tmp:
        for method in args.methods:
            params = method_params(method, paths.configs)
            cands = candidates(method, params)
            scores = [run_candidate(method, c, args.jobs, Path(tmp)) for c in cands]
            table = summarise(method, cands, scores)
            tables.append(table)
            choice = {k: v for k, v in table[table.chosen].iloc[0].items() if k in cands[0]}
            choice = {k: (int(v) if float(v).is_integer() and k != "finetune_lr" else v)
                      for k, v in choice.items()}  # fmt: skip
            note = (
                f"chosen by scripts/select_transfer_hparams.py, {date.today()}, {current_git_sha()}"
            )
            write_choice(paths.configs / "models" / f"{method}.yaml", choice, note)
            log.info("%s: %s", method, choice)
    pd.concat(tables, ignore_index=True).to_csv(out, index=False, float_format="%.6g")
    log.info("grid in %s", out)


if __name__ == "__main__":
    main()
