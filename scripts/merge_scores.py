"""Merge the scores of Kaggle jobs into results/runs/<experiment>/scores.parquet.

uv run python scripts/merge_scores.py results/kaggle/<job>/results/runs [...]

Every <experiment>/scores.parquet under the given folders is added to the local file of the
same experiment. One row is kept per unit (the newest, which only a re-run of a unit makes).

The configuration hash of a row covers the resolved experiment, its --subjects and --methods
subsets included, so shards of one experiment carry different hashes. Each file is checked
instead: the hash its own subjects and methods give under the current configs must equal
the stored one, so a row made with other settings is refused. Prints the commits each
method's rows come from.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from sixthfinger.config import config_hash, load_data_config, load_protocol_config
from sixthfinger.evaluation.runner import UNIT_KEYS, load_experiment, method_params, resolve
from sixthfinger.paths import get_paths


def expected_hashes(experiment: str, rows: pd.DataFrame) -> dict[str, str]:
    """The row hash of each method for a run over exactly these subjects and methods."""
    paths, data_cfg, proto = get_paths(), load_data_config(), load_protocol_config()
    cfg = paths.configs / "experiments" / f"{experiment}.yaml"
    subjects, methods = sorted(set(rows.subject)), sorted(set(rows.method))
    exp = resolve(load_experiment(cfg, proto), proto, data_cfg, subjects, methods)
    base = config_hash(data_cfg, proto, exp)
    out = {}
    for m in methods:
        params = {**method_params(m, paths.configs), **exp.params.get(m, {})}
        payload = base + json.dumps(params, sort_keys=True)
        out[m] = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return out


def check(experiment: str, f: Path) -> pd.DataFrame:
    rows = pd.read_parquet(f)
    expected = expected_hashes(experiment, rows)
    for method, g in rows.groupby("method"):
        if set(g.config_hash) != {expected[method]}:
            raise SystemExit(f"{f}: {method} rows were made with other settings")
    return rows


def merge(experiment: str, files: list[Path], out: Path) -> pd.DataFrame:
    frames = ([pd.read_parquet(out)] if out.exists() else []) + [
        check(experiment, f) for f in files
    ]
    scores = pd.concat(frames, ignore_index=True)
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
