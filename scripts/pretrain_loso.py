"""Pre-train one EEGNet per target subject on every other subject (P07 step 4.4).

uv run python scripts/pretrain_loso.py                      # all 24 targets, aligned, unmirrored
uv run python scripts/pretrain_loso.py --targets sub-01 sub-03
uv run python scripts/pretrain_loso.py --mirror             # the mirrored arm for RQ4

Runs the same on the Mac and in a Kaggle GPU notebook (point --epochs-dir at the mounted
dataset). A model whose file and manifest entry both exist is skipped, so a run that stops
resumes where it stopped.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

from sixthfinger.config import load_data_config
from sixthfinger.data.epochs import load_windows, manifest_sha
from sixthfinger.evaluation.runner import method_params
from sixthfinger.models.deep import (
    prepare_inputs,
    pretrain_loso,
    pretrained_name,
    write_manifest,
)
from sixthfinger.paths import current_git_sha, get_paths

log = logging.getLogger("pretrain")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--targets", nargs="+", default=None, help="default: every subject")
    ap.add_argument("--mirror", action="store_true")
    ap.add_argument("--unaligned", action="store_true", help="the _raw models (eegnet_pooled only)")
    ap.add_argument("--permute-labels", action="store_true", help="the _perm no-signal models")
    ap.add_argument("--epochs-dir", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=Path("models/pretrained"))
    ap.add_argument("--device", default=None, help="override the recipe's device")
    ap.add_argument("--max-epochs", type=int, default=None, help="smoke tests only")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    paths, data_cfg = get_paths(), load_data_config()
    epochs_dir = args.epochs_dir or paths.epochs
    cfg = method_params("eegnet_ea_ft", paths.configs)
    if args.device:
        cfg["device"] = args.device
    if args.max_epochs:
        cfg["pretrain"] = {**cfg["pretrain"], "max_epochs": args.max_epochs}
    aligned = not args.unaligned
    targets = args.targets or list(data_cfg.subjects.ids)
    manifest_path = args.out / "manifest.json"
    done = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    todo = [
        t
        for t in targets
        if not (
            (args.out / pretrained_name(t, args.mirror, aligned, args.permute_labels)).exists()
            and pretrained_name(t, args.mirror, aligned, args.permute_labels) in done
        )
    ]
    log.info("%d of %d targets to pre-train", len(todo), len(targets))
    if not todo:
        return

    X, md = load_windows(epochs_dir, data_cfg, mirror=args.mirror)
    ready = prepare_inputs(X, md.subject.to_numpy(), cfg, aligned)
    del X
    # On Kaggle the repository has no .git; the notebook passes the commit it was built from.
    provenance = {
        "git_sha": os.environ.get("SIXTHFINGER_GIT_SHA") or current_git_sha(),
        "data_manifest_sha": manifest_sha(epochs_dir),
        "recipe": cfg,
    }
    for target in todo:
        entry = pretrain_loso(
            target, cfg, ready, md, data_cfg, args.out, args.mirror, aligned, args.permute_labels
        )
        write_manifest([{**entry, **provenance}], manifest_path)


if __name__ == "__main__":
    main()
