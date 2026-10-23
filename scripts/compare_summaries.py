"""Print every number in results/summary/*.csv that differs from a git ref.

uv run python scripts/compare_summaries.py HEAD~1
uv run python scripts/compare_summaries.py 606200f --record results/summary/summary_rerun_repro.csv

Exit code 1 when a summary changed, so a refactor that should not move any result can
be checked in one command (no-regression rule, 10-SOURCE-OF-TRUTH.md section 4).

With --record, every file of results/summary and results/audit is also compared with the ref
byte for byte; a table that is not byte-identical has the columns it had at the ref compared
value by value, and a column the ref did not have is listed, not compared. One row per file goes
to the record: how a re-run that may only add files and columns shows that it moved nothing.
The exit code then counts only files that changed or disappeared.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from sixthfinger.evaluation.exploratory import json_diff, table_diff
from sixthfinger.paths import current_git_sha, find_root

FOLDERS = ("results/summary", "results/audit")


def _old(ref: str, rel: str, root: Path) -> pd.DataFrame | None:
    proc = subprocess.run(
        ["git", "show", f"{ref}:{rel}"], cwd=root, capture_output=True, text=True, check=False
    )
    return pd.read_csv(io.StringIO(proc.stdout)) if proc.returncode == 0 else None


def _old_bytes(ref: str, rel: str, root: Path) -> bytes | None:
    proc = subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=root, capture_output=True)
    return proc.stdout if proc.returncode == 0 else None


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


def _sha(data: bytes | None) -> str:
    return hashlib.sha256(data).hexdigest()[:16] if data is not None else ""


def record(ref: str, root: Path, out: Path) -> pd.DataFrame:
    """One row per results file: unchanged, new columns only, new, or changed against ref."""
    listed = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", ref, "--", *FOLDERS],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout.split()  # fmt: skip
    now = [p.relative_to(root).as_posix() for f in FOLDERS for p in (root / f).iterdir()]
    skip = out.resolve().relative_to(root).as_posix()
    rows = []
    for rel in sorted((set(listed) | {p for p in now if (root / p).is_file()}) - {skip}):
        before = _old_bytes(ref, rel, root) if rel in listed else None
        path = root / rel
        after = path.read_bytes() if path.is_file() else None
        row = dict(file=rel, sha256_before=_sha(before), sha256_after=_sha(after),
                   byte_identical=before == after, new_columns="")  # fmt: skip
        if before is None or after is None:
            row["status"] = "new" if before is None else "removed"
        elif before == after:
            row["status"] = "unchanged"
        elif rel.endswith(".csv"):
            old, new = (pd.read_csv(io.BytesIO(b)) for b in (before, after))
            res = table_diff(new, old, ignore=())
            added = [c for c in new.columns if c not in old.columns]
            row |= {k: res[k] for k in ("rows", "rows_before", "cells_differing", "max_abs_diff")}
            row["new_columns"] = ";".join(added)
            row["status"] = "new columns only" if res["identical"] and added else "changed"
        elif rel.endswith(".json"):
            res = json_diff(json.loads(after), json.loads(before))
            row |= {k: res[k] for k in ("rows", "rows_before", "cells_differing", "max_abs_diff")}
            row["status"] = "changed"
        else:
            row["status"] = "changed"
        rows.append(row)
    cols = ["file", "status", "byte_identical", "new_columns", "rows", "rows_before",
            "cells_differing", "max_abs_diff", "sha256_before", "sha256_after"]  # fmt: skip
    table = pd.DataFrame(rows).reindex(columns=cols)
    table = table.assign(ref=ref, git_sha=current_git_sha())
    table.to_csv(out, index=False, float_format="%.6g")
    return table


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ref", nargs="?", default="HEAD", help="git ref to compare against")
    ap.add_argument("--record", type=Path, help="also write the file-by-file record here")
    args = ap.parse_args()
    root = find_root()
    changed = compare(args.ref, root)
    if args.record:
        table = record(args.ref, root, args.record)
        print(table.status.value_counts().to_string())
        changed = int(table.status.isin(["changed", "removed"]).sum())
    sys.exit(1 if changed else 0)


if __name__ == "__main__":
    main()
