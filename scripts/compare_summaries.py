"""Print every number in results/summary/*.csv that differs from a git ref.

uv run python scripts/compare_summaries.py HEAD~1

Exit code 1 when a summary changed, so a refactor that should not move any result can
be checked in one command (no-regression rule, 10-SOURCE-OF-TRUTH.md section 4).
"""

from __future__ import annotations

import argparse
import io
import subprocess
import sys
from pathlib import Path

import pandas as pd

from sixthfinger.paths import find_root


def _old(ref: str, rel: str, root: Path) -> pd.DataFrame | None:
    proc = subprocess.run(
        ["git", "show", f"{ref}:{rel}"], cwd=root, capture_output=True, text=True, check=False
    )
    return pd.read_csv(io.StringIO(proc.stdout)) if proc.returncode == 0 else None


def compare(ref: str, root: Path) -> int:
    changed = 0
    for path in sorted((root / "results" / "summary").glob("*.csv")):
        rel = path.relative_to(root).as_posix()
        old, new = _old(ref, rel, root), pd.read_csv(path)
        if old is None:
            print(f"new file: {rel}")
            continue
        if old.equals(new):
            continue
        changed += 1
        print(f"changed: {rel} ({old.shape} -> {new.shape})")
        if old.shape != new.shape or list(old.columns) != list(new.columns):
            continue
        num = old.select_dtypes("number").columns
        diff = (new[num] - old[num]).abs().max()
        print(diff[diff > 0].to_string())
        other = [c for c in old.columns if c not in num]
        for col in other:
            n = int((old[col].astype(str) != new[col].astype(str)).sum())
            if n:
                print(f"{col}: {n} values differ")
    return changed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ref", nargs="?", default="HEAD", help="git ref to compare against")
    args = ap.parse_args()
    sys.exit(1 if compare(args.ref, find_root()) else 0)


if __name__ == "__main__":
    main()
