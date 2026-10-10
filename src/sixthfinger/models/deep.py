"""EEGNet and ShallowConvNet trained through braindecode with the pre-registered recipe (3.6).

The recipe lives in configs/models/<method>.yaml and arrives here as `cfg`. Networks see
microvolts, not volts: inputs of ~1e-6 train badly.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from braindecode import EEGClassifier
from braindecode.models import EEGNet, ShallowFBCSPNet
from skorch.callbacks import EarlyStopping, LRScheduler
from skorch.dataset import Dataset
from skorch.helper import predefined_split

from sixthfinger.config import DataConfig
from sixthfinger.models.registry import Batch, register
from sixthfinger.preprocessing.alignment import align_by_subject

log = logging.getLogger(__name__)

ARCH = {"EEGNet": EEGNet, "ShallowFBCSPNet": ShallowFBCSPNet}


def pick_device(pref: str = "auto") -> str:
    if pref != "auto":
        return pref
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def seed_everything(seed: int) -> None:
    # skorch and braindecode draw from the global numpy state, so it is seeded too.
    np.random.seed(seed)  # noqa: NPY002
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def task_label_map(y: np.ndarray) -> tuple[np.ndarray, dict[int, int]]:
    """Task label ids (T3 is {0 rest, 2 SF}) as positions 0..n-1, in ascending order.

    Returns the positions and the id of each position: the same ascending order as
    scikit-learn's classes_, so predict_proba columns line up with the runner's classes.
    """
    ids = np.unique(y)
    pos = {int(c): i for i, c in enumerate(ids)}
    return np.array([pos[int(v)] for v in y], np.int64), {i: int(c) for i, c in enumerate(ids)}


def build_module(cfg: dict, n_chans: int, n_classes: int, n_times: int) -> torch.nn.Module:
    """The bare network, for loading saved weights."""
    return ARCH[cfg["architecture"]](
        n_chans=n_chans, n_outputs=n_classes, n_times=n_times, **cfg["architecture_params"]
    )


def make_classifier(
    cfg: dict,
    n_chans: int,
    n_classes: int,
    n_times: int,
    max_epochs: int,
    lr: float | None = None,
    valid: Dataset | None = None,
    patience: int | None = None,
    seed: int = 0,
) -> EEGClassifier:
    seed_everything(seed)
    callbacks = [("lr_scheduler", LRScheduler("CosineAnnealingLR", T_max=max_epochs))]
    if valid is not None:
        # Early stopping looks at source validation subjects only, never at the target.
        callbacks.append(
            (
                "early_stopping",
                EarlyStopping(monitor="valid_loss", patience=patience, load_best=True),
            )
        )
    return EEGClassifier(
        ARCH[cfg["architecture"]],
        module__n_chans=n_chans,
        module__n_outputs=n_classes,
        module__n_times=n_times,
        **{f"module__{k}": v for k, v in cfg["architecture_params"].items()},
        optimizer=torch.optim.AdamW,
        optimizer__lr=lr or cfg["optimizer"]["lr"],
        optimizer__weight_decay=cfg["optimizer"]["weight_decay"],
        batch_size=cfg["batch_size"],
        max_epochs=max_epochs,
        train_split=predefined_split(valid) if valid is not None else None,
        device=pick_device(cfg["device"]),
        callbacks=callbacks,
        iterator_train__shuffle=True,
        classes=list(range(n_classes)),
        verbose=0,
    )


class _DeepMethod:
    uses_source = False
    deep = True  # the runner gives deep methods draws_deep instead of draws_classical

    def __init__(self, n_classes: int, **cfg):
        self.n_classes, self.cfg = n_classes, cfg

    def _x(self, X: np.ndarray) -> np.ndarray:
        return (X * self.cfg["input_scale"]).astype(np.float32)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self.clf.predict_proba(self._x(X))


@register("eegnet_scratch")
class EegnetScratch(_DeepMethod):
    """EEGNet trained on the target windows only, a fixed number of epochs, no early stop."""

    def fit(self, target: Batch, source=None, unlabelled=None, seed: int = 0):
        y, _ = task_label_map(target.y)
        _, c, t = target.X.shape
        self.clf = make_classifier(
            self.cfg, c, len(np.unique(y)), t, self.cfg["max_epochs"], seed=seed
        )
        self.clf.fit(self._x(target.X), y)
        return self


@register("shallow_scratch")
class ShallowScratch(EegnetScratch):
    """ShallowConvNet with its own recipe; optional, never in a confirmatory comparison."""


# Pre-training for the transfer methods (P07 step 4.4) ----------------------------------------


def pretrained_name(target: str, mirror: bool, aligned: bool) -> str:
    return f"eegnet_loso_{target}_{'ea_' if aligned else ''}{'mir' if mirror else 'raw'}.pt"


def pretrain_sources(target: str, data_cfg: DataConfig) -> list[str]:
    """Every subject outside the target's split group, so a linked partner never trains it."""
    group = data_cfg.split_group(target)
    return [s for s in data_cfg.subjects.ids if data_cfg.split_group(s) != group]


def pretrain_loso(
    target: str,
    cfg: dict,
    X_all: np.ndarray,
    md_all: pd.DataFrame,
    data_cfg: DataConfig,
    out_dir: Path,
    mirror: bool = False,
    aligned: bool = True,
) -> dict:
    """Pre-train one EEGNet for one target on every other subject (three classes, T2).

    X_all: (n, 40, n_times) volts with md_all rows aligned; mirroring is already applied by
    the caller when `mirror` is set. Each source subject is aligned with its own reference
    over all of its windows (pre-registration 3.6). Three source subjects, drawn with the
    recipe's seed, are held out for early stopping. Returns the manifest entry.
    """
    p = cfg["pretrain"]
    sources = pretrain_sources(target, data_cfg)
    rng = np.random.default_rng(p["seed"])
    val_subjects = sorted(rng.choice(sorted(sources), size=p["validation_subjects"], replace=False))
    train_subjects = sorted(set(sources) - set(val_subjects))
    subjects = md_all.subject.to_numpy()
    tr, va = np.isin(subjects, train_subjects), np.isin(subjects, val_subjects)
    used = set(subjects[tr | va])
    if data_cfg.split_group(target) in {data_cfg.split_group(s) for s in used}:
        raise AssertionError(f"{target} or a linked subject is in its own pre-training data")
    X = X_all[tr | va]
    if aligned:
        X = align_by_subject(X, subjects[tr | va])
    X = (X * cfg["input_scale"]).astype(np.float32)
    y = md_all.label.to_numpy()[tr | va]
    in_tr = tr[tr | va]
    valid = Dataset(X[~in_tr], y[~in_tr])
    clf = make_classifier(
        cfg,
        X.shape[1],
        len(np.unique(y)),
        X.shape[2],
        p["max_epochs"],
        valid=valid,
        patience=p["early_stopping_patience"],
        seed=p["seed"],
    )
    t0 = time.perf_counter()
    clf.fit(X[in_tr], y[in_tr])
    seconds = time.perf_counter() - t0
    out_dir.mkdir(parents=True, exist_ok=True)
    name = pretrained_name(target, mirror, aligned)
    tmp = out_dir / f"{name}.tmp"
    torch.save(clf.module_.state_dict(), tmp)
    tmp.replace(out_dir / name)
    history = [
        {k: h.get(k) for k in ("epoch", "train_loss", "valid_loss", "valid_acc")}
        for h in clf.history
    ]
    best = min(history, key=lambda h: h["valid_loss"])
    log.info(
        "%s: %d epochs, best valid loss %.4f at epoch %d (%.0f s)",
        name,
        len(history),
        best["valid_loss"],
        best["epoch"],
        seconds,
    )
    return {
        "file": name,
        "target": target,
        "mirror": mirror,
        "aligned": aligned,
        "train_subjects": train_subjects,
        "validation_subjects": val_subjects,
        "n_train_windows": int(in_tr.sum()),
        "n_valid_windows": int((~in_tr).sum()),
        "epochs_run": len(history),
        "best_epoch": best["epoch"],
        "best_valid_loss": best["valid_loss"],
        "seconds": round(seconds, 1),
        "device": pick_device(cfg["device"]),
        "torch": torch.__version__,
        "history": history,
    }


def write_manifest(entries: list[dict], path: Path) -> None:
    """Merge entries into the pre-training manifest, one per model file."""
    old = json.loads(path.read_text()) if path.exists() else {}
    old.update({e["file"]: e for e in entries})
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(dict(sorted(old.items())), indent=2))
    tmp.replace(path)
