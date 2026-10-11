#!/usr/bin/env bash
# Show a job's status and, once it has finished, download its output to results/kaggle/<name>/.
#   bash notebooks/kaggle/fetch.sh <name>
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
user="${KAGGLE_USER:-rajveeerr}"
status="$(uvx --from kaggle kaggle kernels status "$user/sfb-$1")"
echo "$status"
case "$status" in
  *COMPLETE* | *ERROR* | *CANCEL*)
    mkdir -p "results/kaggle/$1"
    uvx --from kaggle kaggle kernels output "$user/sfb-$1" -p "results/kaggle/$1" -o -q
    echo "output in results/kaggle/$1"
    ;;
esac
