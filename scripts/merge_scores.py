"""Merge the scores of Kaggle jobs into results/runs/<experiment>/scores.parquet.

uv run python scripts/merge_scores.py results/kaggle/<job>/results/runs [...]

Every <experiment>/scores.parquet under the given folders is added to the local file of the
same experiment. One row is kept per unit (the newest, which only a re-run of a unit makes);
rows of one method made with other settings (config_hash) are refused, as a resume would
refuse them. Prints the commits each method's rows come from.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from sixthfinger.evaluation.runner import UNIT_KEYS
from sixthfinger.paths import get_paths


def merge(experiment: str, files: list[Path], out: Path) -> pd.DataFrame:
    frames = [pd.read_parquet(f) for f in ([out] if out.exists() else []) + files]
    scores = pd.concat(frames, ignore_index=True)
    for method, rows in scores.groupby("method"):
        if (rows.config_hash != rows.config_hash.iloc[0]).any():
            raise SystemExit(f"{experiment}: {method} rows made with different settings")
    scores = scores.sort_values("created_at")
    scores = scores[~scores[UNIT_KEYS].astype(str).duplicated(keep="last")]
    for col in ("k", "fold"):
        scores[col] = pd.to_numeric(scores[col]).astype("Int64")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    scores.to_parquet(tmp, index=False)
    tmp.replace(out)
    return scores


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folders", nargs="+", type=Path)
    args = ap.parse_args()
    runs = get_paths().runs
    found: dict[str, list[Path]] = {}
    for folder in args.folders:
        for f in sorted(folder.glob("*/scores.parquet")):
            found.setdefault(f.parent.name, []).append(f)
    for experiment, files in sorted(found.items()):
        scores = merge(experiment, files, runs / experiment / "scores.parquet")
        shas = scores.groupby("method").git_sha.unique().map(sorted).to_dict()
        print(f"{experiment}: {len(scores)} rows; commits per method: {shas}")


if __name__ == "__main__":
    main()
