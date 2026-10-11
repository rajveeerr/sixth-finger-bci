#!/usr/bin/env bash
# Build the private Kaggle datasets that job_kernel.py reads, then create them or add a version.
#   bash notebooks/kaggle/bundle.sh          # the code and the epoch cache
#   bash notebooks/kaggle/bundle.sh --code   # the code only (the cache has not changed)
# Run from the repository root on a committed tree. The code is a git archive of HEAD with its
# commit id (GIT_SHA) and the pre-registration tags HEAD descends from (PREREG): a bundle has
# no git history, so the runner's pre-registration gate reads that file instead.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
if [ -n "$(git status --porcelain -- src configs scripts pyproject.toml uv.lock)" ]; then
  echo "commit src, configs, scripts, pyproject.toml and uv.lock first: the bundle is a git archive" >&2
  exit 1
fi
code_only=false
[ "${1:-}" = "--code" ] && code_only=true
user="${KAGGLE_USER:-rajveeerr}"
kaggle=(uvx --from kaggle kaggle)
work="$(mktemp -d)"

code="$work/code"
mkdir -p "$code"
git archive --format=tar HEAD src configs scripts pyproject.toml >"$code/code.tar"
git rev-parse --short HEAD >"$work/GIT_SHA"
: >"$work/PREREG"
for tag in prereg-v1 prereg-rq5-v1; do
  if git merge-base --is-ancestor "$tag" HEAD 2>/dev/null; then
    echo "$tag $(git rev-parse --short "$tag^{commit}")" >>"$work/PREREG"
  fi
done
tar -rf "$code/code.tar" -C "$work" GIT_SHA PREREG
gzip "$code/code.tar"
printf '{"title": "sixth-finger-bci-code", "id": "%s/sixth-finger-bci-code", "licenses": [{"name": "other"}]}\n' "$user" >"$code/dataset-metadata.json"
parts=(code)

if ! $code_only; then
  epochs="$work/epochs"
  mkdir -p "$epochs"
  # APFS clones: no extra disk space for the 1.4 GB cache.
  cp -c data/derived/epochs/*.npz data/derived/epochs/metadata.parquet data/derived/epochs/manifest.json "$epochs/"
  printf '{"title": "sixth-finger-bci-epochs", "id": "%s/sixth-finger-bci-epochs", "licenses": [{"name": "other"}]}\n' "$user" >"$epochs/dataset-metadata.json"
  parts+=(epochs)
fi

for d in "${parts[@]}"; do
  slug="$user/sixth-finger-bci-$d"
  if "${kaggle[@]}" datasets status "$slug" >/dev/null 2>&1; then
    "${kaggle[@]}" datasets version -p "$work/$d" -m "commit $(cat "$work/GIT_SHA")" -q
  else
    "${kaggle[@]}" datasets create -p "$work/$d" -q
  fi
done
echo "uploaded ${parts[*]} at $(cat "$work/GIT_SHA") (pre-registration: $(tr '\n' ' ' <"$work/PREREG"))"
