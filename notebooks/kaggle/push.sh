#!/usr/bin/env bash
# Push one job to Kaggle as its own private notebook, so several jobs can run side by side.
#   bash notebooks/kaggle/push.sh <name> <cpu|gpu> [--models] <kind> [args...]
#   bash notebooks/kaggle/push.sh pretrain gpu pretrain
#   bash notebooks/kaggle/push.sh dl-baselines gpu run configs/experiments/dl_baselines.yaml
# kind: "pretrain" (scripts/pretrain_loso.py) or "run" (sixthfinger run). --models mounts the
# pre-trained EEGNets, the output of the "pretrain" job. Inputs come from bundle.sh: push after
# bundling the commit you want to run. Collect the output with fetch.sh <name>.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
name="$1"
accel="$2"
shift 2
models=false
if [ "${1:-}" = "--models" ]; then
  models=true
  shift
fi
user="${KAGGLE_USER:-rajveeerr}"
work="$(mktemp -d)"
python3 - "$work" "$@" <<'PY'
import json
import sys
from pathlib import Path

work, kind, args = sys.argv[1], sys.argv[2], sys.argv[3:]
marker = "JOB = {}  # filled in by push.sh"
src = Path("notebooks/kaggle/job_kernel.py").read_text()
assert src.count(marker) == 1
job = json.dumps({"kind": kind, "args": args})
Path(work, "kernel.py").write_text(src.replace(marker, f"JOB = {job}"))
PY
gpu=false
[ "$accel" = gpu ] && gpu=true
sources="[]"
$models && sources="[\"$user/sfb-pretrain\"]"
cat >"$work/kernel-metadata.json" <<JSON
{
  "id": "$user/sfb-$name",
  "title": "sfb-$name",
  "code_file": "kernel.py",
  "language": "python",
  "kernel_type": "script",
  "is_private": true,
  "enable_gpu": $gpu,
  "enable_internet": true,
  "dataset_sources": ["$user/sixth-finger-bci-code", "$user/sixth-finger-bci-epochs"],
  "competition_sources": [],
  "kernel_sources": $sources
}
JSON
uvx --from kaggle kaggle kernels push -p "$work"
