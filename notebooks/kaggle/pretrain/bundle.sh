#!/usr/bin/env bash
# Build the two private Kaggle datasets the pre-training notebook reads, then create them or
# add a new version. Run from the repository root on a clean, committed tree.
#   bash notebooks/kaggle/pretrain/bundle.sh
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
if [ -n "$(git status --porcelain -- src configs scripts pyproject.toml)" ]; then
  echo "commit src, configs, scripts and pyproject.toml first: the bundle is a git archive" >&2
  exit 1
fi
user="${KAGGLE_USER:-rajveeerr}"
kaggle=(uvx --from kaggle kaggle)
work="$(mktemp -d)"

code="$work/code"
mkdir -p "$code"
git archive --format=tar HEAD src configs scripts pyproject.toml >"$code/code.tar"
git rev-parse --short HEAD >"$work/GIT_SHA"
tar -rf "$code/code.tar" -C "$work" GIT_SHA
gzip "$code/code.tar"
printf '{"title": "sixth-finger-bci-code", "id": "%s/sixth-finger-bci-code", "licenses": [{"name": "other"}]}\n' "$user" >"$code/dataset-metadata.json"

epochs="$work/epochs"
mkdir -p "$epochs"
# APFS clones: no extra disk space for the 1.4 GB cache.
cp -c data/derived/epochs/*.npz data/derived/epochs/metadata.parquet data/derived/epochs/manifest.json "$epochs/"
printf '{"title": "sixth-finger-bci-epochs", "id": "%s/sixth-finger-bci-epochs", "licenses": [{"name": "other"}]}\n' "$user" >"$epochs/dataset-metadata.json"

for d in code epochs; do
  slug="$user/sixth-finger-bci-$d"
  if "${kaggle[@]}" datasets status "$slug" >/dev/null 2>&1; then
    "${kaggle[@]}" datasets version -p "$work/$d" -m "commit $(cat "$work/GIT_SHA")" -q
  else
    "${kaggle[@]}" datasets create -p "$work/$d" -q
  fi
done
echo "uploaded code at $(cat "$work/GIT_SHA") and the epoch cache; bundle in $work"
