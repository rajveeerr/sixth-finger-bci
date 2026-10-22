"""Exploratory, added after the results: pre-training on other patients plus healthy grasp
imagery, then fine-tuning, for AH vs SF (T1_ah_vs_sf); and a cross-day grasp benchmark.

One part at a time, one process at a time, in this order:

  S="uv run python scripts/ex3_grasp_pretraining.py"
  $S --part fetch          # day 1 and day 2 of the 15 grasp people from OSF (4.2 GB)
  $S --part convert        # our 40 channels, our preprocessing, the imagery period, cached
  $S --part equivalence    # this pre-training code against the repo's pretrain_loso (cpu)
  $S --part timing         # one epoch on cpu and on mps; the faster is used
  $S --part check_b        # this fine-tuning path reproduces arm B of ex1_transfer_ah_sf
  $S --part benchmark      # grasp people, day 1 -> day 2, ts_lr and csp_lda
  $S --part pretrain_g     # G: grasp people only (unmirrored and mirrored)
  $S --part select_g       # G's fine-tuning values, run 01 -> run 02 of sub-01 and sub-03
  $S --part finetune --arm G
  $S --part pretrain_gp --targets sub-01
  $S --part projection     # fixes P's targets by the rule in the settings
  $S --part pretrain_gp    # add --targets sub-XX to keep one target per process
  $S --part finetune --arm GP
  $S --part pretrain_p
  $S --part finetune --arm P
  $S --part summary
  $S --part finetune --arm GP_central   # refuses unless GP beats its primary control

Settings: configs/experiments/ex3_grasp_pretraining.yaml, fixed before any score; runs 03-04
are only scored. The GP pre-training took 10.9 hours of device time: `--part carry --research
DIR` takes the fine-tuned values of GP, G and P, G's selection and the one-time checks from
the exploratory run in DIR with the commit that holds them; `--part finetune --arm X --subjects
...` re-runs a few patients beside them; `--part repro --research DIR` compares every output.
Writes results/summary/ex3_grasp_pretraining_*.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import time
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import yaml

from sixthfinger.data.channels import CENTRAL_14, CHANNELS_40, hemiplegia_side
from sixthfinger.paths import get_paths

# Data-loading workers re-import this file each epoch, so its top level stays light: the
# project's heavier modules are imported where they are used.
NAME = "ex3_grasp_pretraining"
PATHS = get_paths()
CONFIG = yaml.safe_load((PATHS.configs / "experiments" / f"{NAME}.yaml").read_text())
RUNS_DIR = PATHS.runs / NAME
EXTERNAL = PATHS.data / "external" / "bcicomp2020_track4"
DERIVED = PATHS.derived / "bcicomp2020_track4"
MODELS = PATHS.derived / "grasp_pretraining"
B_MODELS = PATHS.models / "pretrained"
WORKERS = 2
MIN_FREE = 2.5 * 2**30  # bytes; df -h reports GiB, so this is the stricter reading of 2.5 GB
SEEDS = [0, 1, 2]
ARMS = ["GP", "G", "P", "GP_central"]

GRASP_CLASSES = ["cylindrical", "spherical", "lumbrical"]
GRASP_PEOPLE = [f"S{n:02d}" for n in range(1, 16)]
# OSF file guids, copied from moabb.datasets.bcicomp2020_upper_limb (MOABB 1.7.2). Day 3
# ("test") is left out on purpose: its labels come from an answer sheet with repeated orders.
OSF = {
    ("day1", 1): "yzmut", ("day1", 2): "9n8zv", ("day1", 3): "h6ry4", ("day1", 4): "atnwe",
    ("day1", 5): "f6c5a", ("day1", 6): "2wu68", ("day1", 7): "dwx36", ("day1", 8): "h6nv7",
    ("day1", 9): "n52yz", ("day1", 10): "tv9rs", ("day1", 11): "hjx5z", ("day1", 12): "whpdu",
    ("day1", 13): "d4js3", ("day1", 14): "xz6ju", ("day1", 15): "9sy8r",
    ("day2", 1): "amnzq", ("day2", 2): "g947y", ("day2", 3): "rhme9", ("day2", 4): "sz4p3",
    ("day2", 5): "qv9c2", ("day2", 6): "p4am3", ("day2", 7): "49byt", ("day2", 8): "b4x8q",
    ("day2", 9): "cpfm6", ("day2", 10): "wjpdy", ("day2", 11): "6vrph", ("day2", 12): "mq9sx",
    ("day2", 13): "67rnu", ("day2", 14): "dkpf8", ("day2", 15): "bq53w",
}  # fmt: skip

log = logging.getLogger(NAME)


def out(name: str) -> Path:
    return PATHS.summary / f"{NAME}_{name}"


def setup_logging() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S")
    for h in (logging.StreamHandler(), logging.FileHandler(RUNS_DIR / "run.log")):
        h.setFormatter(fmt)
        log.addHandler(h)
    log.setLevel(logging.INFO)


def free_bytes() -> int:
    return shutil.disk_usage("/").free


def need_space(n_bytes: int, what: str) -> None:
    free = free_bytes()
    if free - n_bytes < MIN_FREE:
        raise SystemExit(
            f"stop: {what} needs {n_bytes / 2**30:.2f} GiB and would leave "
            f"{(free - n_bytes) / 2**30:.2f} GiB free, under the 2.5 GB floor"
        )


def update_checks(key: str, value) -> None:
    path = out("checks.json")
    checks = json.loads(path.read_text()) if path.exists() else {}
    checks[key] = value
    path.write_text(json.dumps(checks, indent=2) + "\n")


def raw_path(day: str, n: int) -> Path:
    return EXTERNAL / f"S{n:02d}_{day}.mat"


def part_fetch() -> None:
    EXTERNAL.mkdir(parents=True, exist_ok=True)
    for (day, n), guid in sorted(OSF.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        dest = raw_path(day, n)
        url = f"https://osf.io/download/{guid}/"
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD")) as r:
            size = int(r.headers["Content-Length"])
        if dest.exists() and dest.stat().st_size == size:
            continue
        need_space(size, f"S{n:02d} {day}")
        tmp = dest.with_suffix(".part")
        t0 = time.perf_counter()
        with urllib.request.urlopen(url) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f, length=1 << 22)
        if tmp.stat().st_size != size:
            raise SystemExit(f"{dest.name}: got {tmp.stat().st_size} bytes, expected {size}")
        tmp.replace(dest)
        log.info("fetched %s (%.0f MB, %.0f s), %.2f GiB free", dest.name, size / 1e6,
                 time.perf_counter() - t0, free_bytes() / 2**30)  # fmt: skip


def read_grasp_mat(path: Path) -> tuple[np.ndarray, np.ndarray, list[str], np.ndarray]:
    """One day of one grasp person as stored.

    Returns X: (150, 60, 2501) float64 microvolts, labels (150,) 0..2 in GRASP_CLASSES order,
    the channel names, and the file's time axis in ms.
    """
    from scipy.io import loadmat

    epo = loadmat(path, squeeze_me=False, variable_names=["epo"])["epo"]
    x = epo["x"][0, 0]
    y = epo["y"][0, 0]
    names = [str(c[0]) for c in epo["clab"][0, 0][0]]
    classes = [str(c[0]).lower() for c in epo["className"][0, 0][0]]
    if classes != GRASP_CLASSES or x.shape != (2501, 60, 150) or y.shape != (3, 150):
        raise SystemExit(f"{path.name}: unexpected layout {x.shape} {y.shape} {classes}")
    if not (y.sum(axis=0) == 1).all() or float(epo["fs"][0, 0][0, 0]) != 250.0:
        raise SystemExit(f"{path.name}: labels not one-hot or rate not 250 Hz")
    X = np.ascontiguousarray(np.transpose(x, (2, 1, 0)), dtype=np.float64)
    return X, y.argmax(axis=0).astype(np.int64), names, epo["t"][0, 0][0].astype(float)


def car_set(names: list[str]) -> list[str]:
    """Recorded channels that match the authors' 43: our 40 present here, plus Fp1 and Fp2."""
    return [c for c in CHANNELS_40 if c in names] + ["Fp1", "Fp2"]


def convert_one(X_uv: np.ndarray, names: list[str]) -> tuple[np.ndarray, dict]:
    """Our 40 channels, full 10 s trials, volts, float64, plus the numbers the checks keep.

    X_uv: (n, 60, 2501) microvolts as stored (FCz reference).
    """
    import warnings

    import mne

    good = car_set(names)
    missing = [c for c in CHANNELS_40 if c not in names]
    info = mne.create_info(good + missing, 250.0, "eeg")

    def interpolated(X_good: np.ndarray) -> np.ndarray:
        full = np.concatenate(
            [X_good, np.zeros((len(X_good), len(missing), X_good.shape[-1]))], axis=1
        )
        epochs = mne.EpochsArray(full, info, verbose="error")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)  # standard_1005 renamed in MNE 1.13
            montage = mne.channels.make_standard_montage("standard_1005")
        epochs.set_montage(montage, verbose="error")
        epochs.info["bads"] = list(missing)
        epochs.interpolate_bads(reset_bads=True, verbose="error")
        return epochs.get_data(copy=False)

    X = X_uv[:, [names.index(c) for c in good]]
    X = (X - X.mean(axis=-1, keepdims=True)) * 1e-6
    # FCz is this recording's reference, so under the same average it is exactly minus the
    # mean of the 39; kept only to see how close the spline gets.
    fcz_exact = -X.mean(axis=1)
    # Interpolating before the average must give the same answer (the spline keeps constants).
    first = interpolated(X[:10])
    first -= first[:, : len(good)].mean(axis=1, keepdims=True)
    data = interpolated(X - X.mean(axis=1, keepdims=True))
    commute = np.abs(first - data[:10]).max() / np.abs(data[:10]).max()
    del X, first
    order = [info.ch_names.index(c) for c in CHANNELS_40]
    bp = mne.filter.filter_data(data[:, order], 250.0, 5.0, 35.0, verbose="error")
    del data
    fcz_bp = mne.filter.filter_data(fcz_exact, 250.0, 5.0, 35.0, verbose="error")
    fcz = bp[:, CHANNELS_40.index("FCz")]
    win = slice(1500, 2500)
    r = [np.corrcoef(fcz[i, win], fcz_bp[i, win])[0, 1] for i in range(len(bp))]
    rms = np.sqrt((bp[..., win] ** 2).mean(axis=(0, 1)))
    stats = {
        "fcz_spline_vs_exact_r_median": float(np.median(r)),
        "fcz_spline_vs_exact_r_min": float(np.min(r)),
        "car_interp_commute_rel_max": float(commute),
        "rms_last_0.8s_over_first_3.2s": float(rms[800:].mean() / rms[:800].mean()),
    }
    return bp, stats


def evoked_peaks(bp: np.ndarray, t_ms: np.ndarray) -> dict:
    """Latency of the largest trial-averaged response after the cue and after imagery onset."""
    gfp = bp.mean(axis=0).std(axis=0)
    base = gfp[(t_ms >= -5500) & (t_ms < -3500)].mean()
    peaks = {}
    for name, lo in (("cue", -3000), ("imagery", 0)):
        sel = np.flatnonzero((t_ms >= lo - 500) & (t_ms < lo + 500))
        peak = sel[gfp[sel].argmax()]
        peaks[f"{name}_peak_ms_from_onset"] = float(t_ms[peak] - lo)
        peaks[f"{name}_peak_over_baseline"] = float(gfp[peak] / base)
    return peaks


def imagery_window(bp: np.ndarray) -> np.ndarray:
    """The 4 s imagery period, samples [1500, 2500), float32 volts."""
    return np.ascontiguousarray(bp[..., 1500:2500], dtype=np.float32)


def part_convert() -> None:
    DERIVED.mkdir(parents=True, exist_ok=True)
    rows, stats = [], {}
    for n in range(1, 16):
        if not all(raw_path(day, n).exists() for day in ("day1", "day2")):
            continue
        for day in ("day1", "day2"):
            person = f"S{n:02d}"
            dest = DERIVED / f"{person}_{day}.npy"
            X_uv, y, names, t_ms = read_grasp_mat(raw_path(day, n))
            if not dest.exists():
                bp, s = convert_one(X_uv, names)
                s |= evoked_peaks(bp, t_ms)
                s["window_t_ms"] = [float(t_ms[1500]), float(t_ms[2499])]
                win = imagery_window(bp)
                need_space(win.nbytes, f"{dest.name}")
                np.save(dest.with_suffix(".tmp.npy"), win)
                dest.with_suffix(".tmp.npy").replace(dest)
                stats[f"{person}_{day}"] = s
                log.info("%s %s: %s", person, day, {k: np.round(v, 3) for k, v in s.items()})
                del bp, win
            rows += [
                dict(person=person, day=day, trial=i, label=int(v), label_name=GRASP_CLASSES[v])
                for i, v in enumerate(y)
            ]
            del X_uv
    pd.DataFrame(rows).to_csv(DERIVED / "labels.csv", index=False)
    if stats:
        old_path = DERIVED / "conversion_stats.json"
        old = json.loads(old_path.read_text()) if old_path.exists() else {}
        old_path.write_text(json.dumps(old | stats, indent=2) + "\n")
    if len(rows) == 2 * 150 * len(GRASP_PEOPLE):
        conversion_checks()


def conversion_checks() -> None:
    labels = pd.read_csv(DERIVED / "labels.csv")
    stats = json.loads((DERIVED / "conversion_stats.json").read_text())
    shapes = {}
    for f in sorted(DERIVED.glob("S*_day*.npy")):
        X = np.load(f, mmap_mode="r")
        shapes[f.stem] = [list(X.shape), str(X.dtype)]
    s = pd.DataFrame(stats).T
    with_names = car_set(read_grasp_mat(raw_path("day1", 1))[2])
    counts = {d: g.label_name.value_counts().to_dict() for d, g in labels.groupby("day")}
    update_checks(
        "grasp_conversion",
        {
            "files": len(shapes),
            "shapes_all_150_40_1000_float32": all(
                v == [[150, 40, 1000], "float32"] for v in shapes.values()
            ),
            "trials_per_class_per_day_per_person": sorted(
                set(labels.groupby(["person", "day", "label"]).size().tolist())
            ),
            "trials_per_class_by_day": counts,
            "car_channels": with_names,
            "interpolated": ["FCz", "PO5", "PO6"],
            "window_samples": [1500, 2500],
            "window_t_ms_in_file": sorted({tuple(v) for v in s.window_t_ms}),
            "window_check": "the file's own time axis puts t = 0 ms (imagery onset) at sample 1500 "
            "and 3996 ms at sample 2499; the trial-averaged response peaks just after the cue "
            "(t = -3000 ms) and just after imagery onset (t = 0)",
            "cue_peak_ms_from_onset_median": float(s.cue_peak_ms_from_onset.median()),
            "imagery_peak_ms_from_onset_median": float(s.imagery_peak_ms_from_onset.median()),
            "imagery_peak_over_baseline_median": float(s.imagery_peak_over_baseline.median()),
            "fcz_spline_vs_exact_r_median_of_medians": float(
                s.fcz_spline_vs_exact_r_median.median()
            ),
            "fcz_spline_vs_exact_r_min": float(s.fcz_spline_vs_exact_r_min.min()),
            "car_interp_commute_rel_max": float(s.car_interp_commute_rel_max.max()),
            "rms_last_0.8s_over_first_3.2s_median": float(
                s["rms_last_0.8s_over_first_3.2s"].median()
            ),
            "rms_last_0.8s_over_first_3.2s_range": [
                float(s["rms_last_0.8s_over_first_3.2s"].min()),
                float(s["rms_last_0.8s_over_first_3.2s"].max()),
            ],
        },
    )


def npz_member_memmap(path: Path, member: str = "X.npy") -> np.memmap:
    """A stored (uncompressed) npz member opened as a read-only memory map, without a copy."""
    import struct

    with zipfile.ZipFile(path) as z:
        info = z.getinfo(member)
        if info.compress_type != zipfile.ZIP_STORED:
            raise ValueError(f"{path.name}/{member} is compressed")
    with open(path, "rb") as f:
        f.seek(info.header_offset)
        head = f.read(30)
        if head[:4] != b"PK\x03\x04":
            raise ValueError(f"{path.name}: no local header at {info.header_offset}")
        name_len, extra_len = struct.unpack("<HH", head[26:30])
        f.seek(info.header_offset + 30 + name_len + extra_len)
        version = np.lib.format.read_magic(f)
        read = {
            (1, 0): np.lib.format.read_array_header_1_0,
            (2, 0): np.lib.format.read_array_header_2_0,
        }[version]
        shape, fortran, dtype = read(f)
        offset = f.tell()
    return np.memmap(
        path, dtype=dtype, mode="r", offset=offset, shape=shape, order="F" if fortran else "C"
    )


class LazyArray:
    """A memory-mapped window array opened on first use, so a data-loading worker process
    receives a path, not a copy of the data."""

    def __init__(self, path: Path, npz_member: str | None = None):
        self.path, self.member, self._array = path, npz_member, None

    def array(self) -> np.ndarray:
        if self._array is None:
            self._array = (
                npz_member_memmap(self.path, self.member)
                if self.member
                else np.load(self.path, mmap_mode="r")
            )
        return self._array

    def __getitem__(self, idx):
        return self.array()[idx]

    def __len__(self) -> int:
        return self.array().shape[0]

    def __getstate__(self) -> dict:
        return {"path": self.path, "member": self.member, "_array": None}


def patient_rows():
    """Metadata of every cached window in load_windows order, and a memmap per source file."""
    from sixthfinger.config import load_data_config
    from sixthfinger.data.epochs import _settings

    epochs, cfg = PATHS.epochs, load_data_config()
    manifest = json.loads((epochs / "manifest.json").read_text())
    if any(manifest.get(k) != v for k, v in _settings(cfg).items()):
        raise RuntimeError("epoch cache built with other settings")
    md = pd.read_parquet(epochs / "metadata.parquet")
    parts = [rows for _, rows in md.groupby("source_file", sort=True)]
    md = pd.concat(parts, ignore_index=True)
    maps = {name: LazyArray(epochs / name, "X.npy") for name in md.source_file.unique()}
    for name, m in maps.items():
        if len(m) != (md.source_file == name).sum():
            raise RuntimeError(f"{name}: cache and metadata disagree")
    return md, maps


def subject_reference(md: pd.DataFrame, maps: dict, subject: str) -> np.ndarray:
    """prepare_inputs' reference for one subject: all its windows, in load_windows order."""
    from sixthfinger.preprocessing.alignment import reference_matrix

    rows = md[md.subject == subject]
    X = np.concatenate(
        [maps[f][g.row_in_npz.to_numpy()] for f, g in rows.groupby("source_file", sort=True)]
    )
    return reference_matrix(X)


def references(md: pd.DataFrame, maps: dict) -> dict[str, np.ndarray]:
    """Per-subject and per grasp person-day references, cached (they never change)."""
    from sixthfinger.preprocessing.alignment import reference_matrix

    MODELS.mkdir(parents=True, exist_ok=True)
    path = MODELS / "references_patients.npz"
    if not path.exists():
        np.savez(path, **{s: subject_reference(md, maps, s) for s in sorted(md.subject.unique())})
    with np.load(path) as z:
        refs = {k: z[k] for k in z.files}
    path = MODELS / "references_grasp.npz"
    if not path.exists():
        files = sorted(DERIVED.glob("S*_day*.npy"))
        grasp = {f.stem: reference_matrix(np.load(f, mmap_mode="r")) for f in files}
        if len(files) == 2 * len(GRASP_PEOPLE):
            np.savez(path, **grasp)
        return refs | grasp
    with np.load(path) as z:
        return refs | {k: z[k] for k in z.files}


class Windows(torch.utils.data.Dataset):
    """Network inputs read lazily: each window aligned with its own block's reference, then
    scaled to microvolts, exactly as prepare_inputs does for a whole subject at once.

    A block is (array (n, 40, t) float32 volts, rows, reference, channel order or None,
    label ids already shifted to their head's positions). A channel order is applied after
    alignment, which commutes with a channel permutation.
    """

    def __init__(self, blocks: list[tuple], scale: float):
        self.blocks = blocks
        # align() in float64 through BLAS: the same numbers as its einsum (the equivalence
        # check), ten times faster one window at a time.
        self.R64 = [b[2].astype(np.float64) for b in blocks]
        self.scale = np.float32(scale)
        self.index = np.concatenate(
            [
                np.stack([np.full(len(b[1]), i), np.arange(len(b[1]))], 1)
                for i, b in enumerate(blocks)
            ]
        )
        self.y = np.concatenate([b[4] for b in blocks]).astype(np.int64)

    def __len__(self) -> int:
        return len(self.index)

    def __getitem__(self, i: int):
        b, r = self.index[i]
        X, rows, _, order, _ = self.blocks[b]
        x = (self.R64[b] @ np.asarray(X[rows[r]], np.float64)).astype(np.float32) * self.scale
        if order is not None:
            x = x[order]
        return torch.from_numpy(np.ascontiguousarray(x)), self.y[i]


def patient_blocks(md, maps, refs, subjects) -> list[tuple]:
    blocks = []
    for s in subjects:
        rows = md[md.subject == s]
        for f, g in rows.groupby("source_file", sort=True):
            blocks.append((maps[f], g.row_in_npz.to_numpy(), refs[s], None, g.label.to_numpy()))
    return blocks


def grasp_blocks(refs, people, mirror: bool) -> list[tuple]:
    """Grasp windows of `people`, labels 3-5 for the grasp head; mirrored left-right if asked."""
    from sixthfinger.data.channels import mirror_permutation

    labels = pd.read_csv(DERIVED / "labels.csv")
    order = mirror_permutation() if mirror else None
    blocks = []
    for p in people:
        for day in ("day1", "day2"):
            X = LazyArray(DERIVED / f"{p}_{day}.npy")
            y = labels[(labels.person == p) & (labels.day == day)].sort_values("trial").label
            blocks.append((X, np.arange(len(X)), refs[f"{p}_{day}"], order, y.to_numpy() + 3))
    return blocks


class TwoHeads(torch.nn.Module):
    """EEGNet's body with its own final layer (patients) and a second one (grasps)."""

    def __init__(self, net, grasp_head):
        super().__init__()
        self.net, self.grasp_head = net, grasp_head

    def forward(self, x):
        for name, layer in self.net.named_children():
            if name == "final_layer":
                break
            x = layer(x)
        return torch.cat([self.net.final_layer(x), self.grasp_head(x)], dim=1)


def two_heads(cfg: dict, n_chans: int, n_times: int, seed: int) -> TwoHeads:
    """The body and patient head drawn exactly as make_classifier draws a lone EEGNet.

    The grasp head comes from its own generator, so the global stream that later shuffles the
    batches and drives dropout is where it would be without it.
    """
    from sixthfinger.models.deep import build_module, seed_everything

    seed_everything(seed)
    net = build_module(cfg, n_chans, 3, n_times)
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(seed)
        grasp_head = build_module(cfg, n_chans, 3, n_times).final_layer
    return TwoHeads(net, grasp_head)


class HeadwiseCrossEntropy(torch.nn.Module):
    """Ids 0-2 are scored on the patient head (outputs 0-2), 3-5 on the grasp head."""

    def forward(self, logits, y):
        grasp = y >= 3
        own = torch.where(grasp[:, None], logits[:, 3:6], logits[:, 0:3])
        return torch.nn.functional.cross_entropy(own, torch.where(grasp, y - 3, y))


def head_accuracy(head: int):
    def scorer(net, X, y):
        logits = net.predict_proba(X)
        own = logits[:, 3 * head : 3 * head + 3].argmax(1)
        return float((own == np.asarray(y) - 3 * head).mean())

    return scorer


def epoch_logger(tag: str = ""):
    from skorch.callbacks import Callback

    class EpochLog(Callback):
        def on_epoch_end(self, net, **kwargs):
            h = net.history[-1]
            log.info("  %s epoch %d: train %.4f valid %.4f acc %.3f (%.0f s)", tag, h["epoch"],
                     h["train_loss"], h["valid_loss"], h["valid_acc"], h["dur"])  # fmt: skip

    return EpochLog()


def pretrain(
    train: Windows,
    valid: Windows,
    cfg: dict,
    device: str,
    valid_head: int,
    max_epochs: int | None = None,
    tag: str = "",
):
    """pretrain_loso's classifier (make_classifier) around the two-head network."""
    from braindecode import EEGClassifier
    from skorch.callbacks import EarlyStopping, LRScheduler
    from skorch.helper import predefined_split

    p = cfg["pretrain"]
    epochs = max_epochs or p["max_epochs"]
    module = two_heads(cfg, 40, 1000, p["seed"])
    clf = EEGClassifier(
        module,
        criterion=HeadwiseCrossEntropy,
        optimizer=torch.optim.AdamW,
        optimizer__lr=cfg["optimizer"]["lr"],
        optimizer__weight_decay=cfg["optimizer"]["weight_decay"],
        batch_size=cfg["batch_size"],
        max_epochs=epochs,
        train_split=predefined_split(valid),
        device=device,
        callbacks=[
            ("lr_scheduler", LRScheduler("CosineAnnealingLR", T_max=epochs)),
            (
                "early_stopping",
                EarlyStopping(
                    monitor="valid_loss", patience=p["early_stopping_patience"], load_best=True
                ),
            ),
            ("epoch_log", epoch_logger(tag)),
        ],
        callbacks__valid_acc__scoring=head_accuracy(valid_head),
        iterator_train__shuffle=True,
        iterator_train__drop_last=False,
        # Reading and aligning windows overlaps the device. Workers are made afresh each epoch,
        # so the loader draws from the global random stream exactly as without them.
        iterator_train__num_workers=WORKERS,
        iterator_train__persistent_workers=False,
        classes=list(range(6)),
        verbose=0,
    )
    t0 = time.perf_counter()
    clf.fit(train, y=None)
    seconds = time.perf_counter() - t0
    history = [
        {k: h.get(k) for k in ("epoch", "train_loss", "valid_loss", "valid_acc", "dur")}
        for h in clf.history
    ]
    return clf.module_, history, seconds


def recipe() -> dict:
    from sixthfinger.evaluation.runner import method_params

    return method_params("eegnet_ea_ft", PATHS.configs)


def original_entry(target: str) -> dict:
    """Arm B's manifest entry for `target`; the recipe's own draw must give the same split."""
    from sixthfinger.config import load_data_config
    from sixthfinger.models.deep import pretrain_sources

    manifest = json.loads((B_MODELS / "manifest.json").read_text())
    entry = manifest[f"eegnet_loso_{target}_ea_raw.pt"]
    p = recipe()["pretrain"]
    sources = pretrain_sources(target, load_data_config())
    rng = np.random.default_rng(p["seed"])
    val = sorted(rng.choice(sorted(sources), size=p["validation_subjects"], replace=False))
    if (
        val != entry["validation_subjects"]
        or sorted(set(sources) - set(val)) != entry["train_subjects"]
    ):
        raise AssertionError(f"{target}: the recipe's draw differs from the manifest")
    return entry


def save_model(module, out_dir: Path, name: str, entry: dict, head: str) -> None:
    """The body with one head as a plain EEGNet state dict, in the manifest pretrained_path()
    checks."""
    from sixthfinger.models.deep import write_manifest

    out_dir.mkdir(parents=True, exist_ok=True)
    state = module.net.state_dict()
    if head == "grasp":
        state = {
            **state,
            **{f"final_layer.{k}": v for k, v in module.grasp_head.state_dict().items()},
        }
    tmp = out_dir / f"{name}.tmp"
    torch.save({k: v.detach().cpu() for k, v in state.items()}, tmp)
    tmp.replace(out_dir / name)
    write_manifest([entry], out_dir / "manifest.json")


def done(out_dir: Path, name: str) -> bool:
    manifest = out_dir / "manifest.json"
    return (
        (out_dir / name).exists() and manifest.exists() and name in json.loads(manifest.read_text())
    )


DEVICE_OVERRIDE: list[str] = []


def pretrain_device() -> str:
    if DEVICE_OVERRIDE:
        return DEVICE_OVERRIDE[0]
    path = out("checks.json")
    checks = json.loads(path.read_text()) if path.exists() else {}
    if "device_timing" not in checks:
        raise SystemExit("run --part timing first: the device is chosen from it")
    return checks["device_timing"]["chosen"]


def pretrain_patient_target(
    target: str,
    with_grasp: bool,
    out_dir: Path,
    device: str,
    max_epochs: int | None = None,
    md=None,
    maps=None,
) -> dict:
    """One leave-one-subject-out model for one target: GP (with_grasp) or P."""
    name = f"eegnet_loso_{target}_ea_raw.pt"
    cfg = recipe()
    entry0 = original_entry(target)
    if md is None:
        md, maps = patient_rows()
    refs = references(md, maps)
    mirror = with_grasp and hemiplegia_side(target) == "L"
    train_blocks = patient_blocks(md, maps, refs, entry0["train_subjects"])
    if with_grasp:
        train_blocks += grasp_blocks(refs, GRASP_PEOPLE, mirror)
    train = Windows(train_blocks, cfg["input_scale"])
    valid = Windows(
        patient_blocks(md, maps, refs, entry0["validation_subjects"]), cfg["input_scale"]
    )
    module, history, seconds = pretrain(
        train, valid, cfg, device, 0, max_epochs, tag=f"{out_dir.name} {target}"
    )
    best = min(history, key=lambda h: h["valid_loss"])
    entry = {
        "file": name,
        "target": target,
        "mirror": False,
        "aligned": True,
        "permuted": False,
        "train_subjects": entry0["train_subjects"],
        "validation_subjects": entry0["validation_subjects"],
        "grasp_people": GRASP_PEOPLE if with_grasp else [],
        "grasp_mirrored": mirror,
        "n_train_windows": len(train),
        "n_valid_windows": len(valid),
        "n_patient_train_windows": int((train.y < 3).sum()),
        "epochs_run": len(history),
        "best_epoch": best["epoch"],
        "best_valid_loss": best["valid_loss"],
        "seconds": round(seconds, 1),
        "device": device,
        "torch": torch.__version__,
        "recipe": cfg,
        "history": history,
    }
    if (
        entry["n_patient_train_windows"] != entry0["n_train_windows"]
        or len(valid) != entry0["n_valid_windows"]
    ):
        raise AssertionError(f"{target}: window counts differ from the original manifest")
    save_model(module, out_dir, name, entry, "patient")
    log.info("%s %s: %d epochs, best valid loss %.4f at %d (original %.4f at %d), %.0f s",
             out_dir.name, target, len(history), best["valid_loss"], best["epoch"],
             entry0["best_valid_loss"], entry0["best_epoch"], seconds)  # fmt: skip
    return entry


def part_equivalence() -> None:
    """Two epochs of this code path against the repo's pretrain_loso, cpu, same seed.

    Target sub-01 with one training patient (sub-02) and its three validation patients, so
    the repo's in-memory version fits in memory here.
    """
    import tempfile

    from sixthfinger.config import load_data_config
    from sixthfinger.data.epochs import load_windows
    from sixthfinger.models.deep import build_module, prepare_inputs, pretrain_loso

    torch.set_num_threads(2)
    target, train_s = "sub-01", ["sub-02"]
    val_s = original_entry(target)["validation_subjects"]
    cfg = recipe() | {"device": "cpu"}
    cfg["pretrain"] = {**cfg["pretrain"], "max_epochs": 2}
    data_cfg = load_data_config()
    X, md_s = load_windows(PATHS.epochs, data_cfg, subjects=train_s + val_s)
    ready = prepare_inputs(X, md_s.subject.to_numpy(), cfg, aligned=True)
    del X
    with tempfile.TemporaryDirectory() as tmp:
        entry = pretrain_loso(target, cfg, ready, md_s, data_cfg, Path(tmp))
        net = build_module(cfg, 40, 3, 1000)
        net.load_state_dict(torch.load(Path(tmp) / entry["file"], weights_only=True))
    repo_state = net.state_dict()
    md, maps = patient_rows()
    refs = references(md, maps)
    train = Windows(patient_blocks(md, maps, refs, train_s), cfg["input_scale"])
    valid = Windows(patient_blocks(md, maps, refs, val_s), cfg["input_scale"])
    sel = np.flatnonzero(md_s.subject.isin(train_s).to_numpy())
    lazy = np.stack([train[i][0].numpy() for i in range(len(train))])
    input_diff = float(np.abs(lazy - ready[sel]).max())
    del ready, lazy
    module, history, _ = pretrain(train, valid, cfg, "cpu", 0, max_epochs=2)
    mine = module.net.state_dict()
    weight_diff = max(float((mine[k].cpu() - repo_state[k]).abs().max()) for k in repo_state)
    loss_diff = max(
        abs(a["train_loss"] - b["train_loss"]) + abs(a["valid_loss"] - b["valid_loss"])
        for a, b in zip(history, entry["history"], strict=True)
    )
    result = {
        "setup": "target sub-01, train sub-02, validation as the manifest, 2 epochs, cpu, seed 0",
        "input_max_abs_diff": input_diff,
        "weights_max_abs_diff": weight_diff,
        "loss_max_abs_diff": loss_diff,
        "repo_history": [(h["train_loss"], h["valid_loss"]) for h in entry["history"]],
        "this_history": [(h["train_loss"], h["valid_loss"]) for h in history],
    }
    update_checks("equivalence_with_pretrain_loso", result)
    log.info("equivalence: %s", result)


def part_timing() -> None:
    """One epoch of the two-head pre-training on a fixed small set, on cpu and on mps."""
    torch.set_num_threads(2)
    cfg = recipe()
    md, maps = patient_rows()
    refs = references(md, maps)
    train = Windows(
        patient_blocks(md, maps, refs, ["sub-02", "sub-04"]) + grasp_blocks(refs, ["S01"], False),
        cfg["input_scale"],
    )
    valid = Windows(patient_blocks(md, maps, refs, ["sub-13"]), cfg["input_scale"])
    timing = {"n_train": len(train), "n_valid": len(valid)}
    for device in ("cpu", "mps"):
        if device == "mps" and not torch.backends.mps.is_available():
            continue
        _, history, seconds = pretrain(train, valid, cfg, device, 0, max_epochs=1)
        timing[device] = {
            "seconds_one_epoch": round(seconds, 1),
            "finite": bool(np.isfinite(history[0]["valid_loss"])),
        }
    ok = [d for d in ("cpu", "mps") if d in timing and timing[d]["finite"]]
    timing["chosen"] = min(ok, key=lambda d: timing[d]["seconds_one_epoch"])
    update_checks("device_timing", timing)
    log.info("timing: %s", timing)


def pre_subjects() -> list[str]:
    from sixthfinger.config import load_data_config
    from sixthfinger.evaluation.exploratory import pre_subjects

    return pre_subjects(load_data_config())


def part_pretrain_patients(with_grasp: bool, targets: list[str] | None) -> None:
    torch.set_num_threads(2)
    out_dir = MODELS / ("gp" if with_grasp else "p")
    device = pretrain_device()
    md, maps = patient_rows()
    for target in targets or pre_subjects():
        if done(out_dir, f"eegnet_loso_{target}_ea_raw.pt"):
            continue
        pretrain_patient_target(target, with_grasp, out_dir, device, md=md, maps=maps)


def grasp_split() -> tuple[list[str], list[str]]:
    """pretrain_loso's validation draw, over the 15 grasp people."""
    p = recipe()["pretrain"]
    rng = np.random.default_rng(p["seed"])
    val = sorted(rng.choice(sorted(GRASP_PEOPLE), size=p["validation_subjects"], replace=False))
    return sorted(set(GRASP_PEOPLE) - set(val)), [str(v) for v in val]


def part_pretrain_g() -> None:
    torch.set_num_threads(2)
    cfg, device = recipe(), pretrain_device()
    out_dir = MODELS / "g"
    md, maps = patient_rows()
    refs = references(md, maps)
    train_p, val_p = grasp_split()
    for mirror in (False, True):
        name = f"eegnet_grasp_{'mir' if mirror else 'raw'}.pt"
        if done(out_dir, name):
            continue
        train = Windows(grasp_blocks(refs, train_p, mirror), cfg["input_scale"])
        valid = Windows(grasp_blocks(refs, val_p, mirror), cfg["input_scale"])
        module, history, seconds = pretrain(train, valid, cfg, device, 1, tag=f"g {name}")
        best = min(history, key=lambda h: h["valid_loss"])
        entry = {
            "file": name,
            "mirror": mirror,
            "train_people": train_p,
            "validation_people": val_p,
            "n_train_windows": len(train),
            "n_valid_windows": len(valid),
            "epochs_run": len(history),
            "best_epoch": best["epoch"],
            "best_valid_loss": best["valid_loss"],
            "seconds": round(seconds, 1),
            "device": device,
            "torch": torch.__version__,
            "recipe": cfg,
            "history": history,
        }
        save_model(module, out_dir, name, entry, "grasp")
        log.info("g %s: %d epochs, best valid loss %.4f (acc %.3f) at %d, %.0f s", name,
                 len(history), best["valid_loss"], best["valid_acc"], best["epoch"],
                 seconds)  # fmt: skip


def part_projection() -> None:
    """Wall time projected from the first GP pre-training; fixes P's targets by the rule."""
    entry = json.loads((MODELS / "gp" / "manifest.json").read_text())
    first = entry[sorted(entry)[0]]
    per_window_epoch = first["seconds"] / (first["epochs_run"] * first["n_train_windows"])
    p_windows = first["n_patient_train_windows"]
    started = pd.Timestamp(json.loads(out("checks.json").read_text())["started"])
    elapsed = (pd.Timestamp.now() - started).total_seconds()
    gp_total = first["seconds"] * 22
    p_target = per_window_epoch * first["epochs_run"] * p_windows
    g_total = 2 * per_window_epoch * first["epochs_run"] * 3600
    rest = 3600.0  # fine-tuning, selection, benchmark and summary not hidden behind the GPU
    total_22 = elapsed + gp_total + 22 * p_target + g_total + rest
    total_3 = elapsed + gp_total + 3 * p_target + g_total + rest
    p_targets = pre_subjects() if total_22 <= 8 * 3600 else ["sub-01", "sub-02", "sub-03"]
    projection = {
        "first_target": first["target"],
        "first_seconds": first["seconds"],
        "first_epochs": first["epochs_run"],
        "elapsed_h": round(elapsed / 3600, 2),
        "gp_22_h": round(gp_total / 3600, 2),
        "p_per_target_h": round(p_target / 3600, 2),
        "g_h": round(g_total / 3600, 2),
        "rest_h": rest / 3600,
        "total_with_p22_h": round(total_22 / 3600, 2),
        "total_with_p3_h": round(total_3 / 3600, 2),
        "p_targets": p_targets,
        "primary": "GP vs P" if len(p_targets) == 22 else "GP vs B",
    }
    update_checks("projection", projection)
    log.info("projection: %s", projection)


def p_targets() -> list[str]:
    checks = json.loads(out("checks.json").read_text())
    if "projection" not in checks:
        raise SystemExit("run --part projection after the first GP pre-training")
    return checks["projection"]["p_targets"]


def session_windows(subject: str):
    from sixthfinger.config import load_data_config
    from sixthfinger.data.epochs import load_windows

    X, md = load_windows(PATHS.epochs, load_data_config(), subjects=[subject],
                         sessions=[CONFIG["session"]], labels=CONFIG["classes"])  # fmt: skip
    return X, md.reset_index(drop=True)


def split(md: pd.DataFrame, train_runs, test_runs):
    from sixthfinger.evaluation.leakage import assert_no_leakage

    tr = md.index[md.run.isin(train_runs)].to_numpy()
    te = md.index[md.run.isin(test_runs)].to_numpy()
    assert_no_leakage(md.iloc[tr], md.iloc[te])
    return tr, te


def bal(y, proba) -> float:
    from sixthfinger.evaluation.metrics import score

    return score(y, proba, CONFIG["classes"])["bal_acc"]


def task_proba(m, X):
    from sixthfinger.evaluation.exploratory import task_proba

    return task_proba(m, X, CONFIG["classes"])


def ea_ft(models_dir: Path):
    import sixthfinger.models  # noqa: F401  (registers every method)
    from sixthfinger.models.registry import make_method

    params = recipe() | {"device": "cpu"}
    return make_method("eegnet_ea_ft", n_classes=2, classes=CONFIG["classes"],
                       models_dir=models_dir, mirror=False, **params)  # fmt: skip


class GraspFinetune:
    """The grasp-only body with a new AH/SF output layer; every layer fine-tuned."""

    def __init__(self, model_path: Path, lr: float, epochs: int):
        self.cfg = recipe() | {"device": "cpu"}
        self.model_path, self.lr, self.epochs = model_path, lr, epochs

    def _x(self, X: np.ndarray) -> np.ndarray:
        from sixthfinger.preprocessing.alignment import align

        return (align(X, self.R) * self.cfg["input_scale"]).astype(np.float32)

    def fit(self, X: np.ndarray, y: np.ndarray, seed: int):
        from sixthfinger.models.deep import build_module, make_finetune_classifier, seed_everything
        from sixthfinger.preprocessing.alignment import reference_matrix

        self.R = reference_matrix(X, self.cfg["alignment"]["rel_floor"])
        seed_everything(seed)
        net = build_module(self.cfg, X.shape[1], 2, X.shape[2])
        state = torch.load(self.model_path, weights_only=True, map_location="cpu")
        body = {k: v for k, v in state.items() if not k.startswith("final_layer.")}
        missing, unexpected = net.load_state_dict(body, strict=False)
        if unexpected or not all(k.startswith("final_layer.") for k in missing):
            raise AssertionError(f"body did not load cleanly: {missing} {unexpected}")
        self.clf = make_finetune_classifier(self.cfg, net, 2, self.epochs, self.lr, seed=seed)
        pos = (y == CONFIG["classes"][1]).astype(np.int64)
        self.clf.fit(self._x(X), pos)
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self.clf.predict_proba(self._x(X)).astype(np.float64)


def g_model(subject: str) -> Path:
    """The grasp-only model on the target's side: mirrored for a left-hemiplegic target."""
    mirror = hemiplegia_side(subject) == "L"
    path = MODELS / "g" / f"eegnet_grasp_{'mir' if mirror else 'raw'}.pt"
    if not done(MODELS / "g", path.name):
        raise SystemExit("run --part pretrain_g first")
    return path


def part_select_g() -> None:
    """P08's rule on run 01 -> run 02 of sub-01 and sub-03; runs 03-04 are never read."""
    import itertools

    torch.set_num_threads(2)
    grid, rows = CONFIG["arm_G"]["grid"], []
    for subject in ("sub-01", "sub-03"):
        X, md = session_windows(subject)
        tr, te = split(md, [1], [2])
        y = md.label.to_numpy()
        for lr, ep in itertools.product(
            sorted(grid["finetune_lr"]), sorted(grid["finetune_epochs"])
        ):
            for seed in SEEDS:
                m = GraspFinetune(g_model(subject), lr, ep).fit(X[tr], y[tr], seed)
                rows.append(dict(subject=subject, finetune_lr=lr, finetune_epochs=ep, seed=seed,
                                 bal_acc=bal(y[te], m.predict_proba(X[te])), n_train=len(tr),
                                 n_test=len(te)))  # fmt: skip
        log.info("select_g %s done", subject)
    df = pd.DataFrame(rows)
    table = df.groupby(["finetune_lr", "finetune_epochs"], sort=True).bal_acc.mean()
    table = table.reset_index().rename(columns={"bal_acc": "mean_bal_acc"})
    table["tie_order"] = range(len(table))
    best = table.sort_values(["mean_bal_acc", "tie_order"], ascending=[False, True]).index[0]
    table["chosen"] = table.index == best
    for s, g in df.groupby("subject"):
        table[f"mean_{s}"] = g.groupby(["finetune_lr", "finetune_epochs"]).bal_acc.mean().to_numpy()
    table.to_csv(out("g_selection.csv"), index=False, float_format="%.6g")
    log.info("g selection:\n%s", table.to_string(index=False))


def g_choice() -> tuple[float, int]:
    t = pd.read_csv(out("g_selection.csv"))
    row = t[t.chosen].iloc[0]
    return float(row.finetune_lr), int(row.finetune_epochs)


def run_rule_central() -> bool:
    table, _ = comparisons()
    primary = table[table.comparison == primary_name()]
    return bool(len(primary) and primary.diff_points.iloc[0] > 0)


def part_finetune(arm: str, subjects: list[str] | None) -> None:
    """Fine-tune and score one arm on runs 03-04; with `subjects`, a re-run beside the values."""
    from sixthfinger.evaluation.leakage import assert_no_leakage
    from sixthfinger.models.registry import Batch
    from sixthfinger.preprocessing.alignment import align

    torch.set_num_threads(2)
    if arm == "GP_central" and not run_rule_central():
        raise SystemExit("GP does not beat its primary control: the central control is not run")
    targets = subjects or (p_targets() if arm == "P" else pre_subjects())
    models_dir = MODELS / {"GP": "gp", "GP_central": "gp", "P": "p", "G": "g"}[arm]
    if arm == "G":
        lr, epochs = g_choice()
    partial = RUNS_DIR / f"values_{arm}.partial.csv"
    rows = pd.read_csv(partial).to_dict("records") if partial.exists() and not subjects else []
    finished = {r["subject"] for r in rows}
    others = [i for i, name in enumerate(CHANNELS_40) if name not in CENTRAL_14]
    for subject in targets:
        if subject in finished:
            continue
        if arm != "G" and not done(models_dir, f"eegnet_loso_{subject}_ea_raw.pt"):
            log.info("finetune %s: %s not pre-trained yet, stopping here", arm, subject)
            break
        t0 = time.perf_counter()
        X, md = session_windows(subject)
        if arm == "GP_central":
            X = X.copy()
            X[:, others] = 0.0
        tr, te = split(md, CONFIG["train_runs"], CONFIG["test_runs"])
        y = md.label.to_numpy()
        train_md = md.iloc[tr]
        assert_no_leakage(train_md, md.iloc[te], unlabelled=train_md)
        new = []
        base = dict(arm=arm, subject=subject, session="pre", n_train=len(tr), n_test=len(te))
        for seed in SEEDS:
            if arm == "G":
                m = GraspFinetune(g_model(subject), lr, epochs).fit(X[tr], y[tr], seed)
                proba, n_nan = m.predict_proba(X[te]), 0
            else:
                m = ea_ft(models_dir).fit(Batch(X[tr], y[tr], train_md),
                                          unlabelled=Batch(X[tr], None, train_md),
                                          seed=seed)  # fmt: skip
                if arm == "GP_central":
                    moved = np.abs(align(X[tr], m.R)[:, others]).max()
                    if moved > 1e-6 * np.abs(align(X[tr], m.R)).max():
                        raise AssertionError(f"{subject}: alignment moved signal into zeros")
                proba, n_nan = task_proba(m, X[te])
            new.append(base | dict(row="finetuned", seed=seed, bal_acc=bal(y[te], proba),
                                   n_registry_nan=n_nan))  # fmt: skip
        if arm != "G":
            m0 = ea_ft(models_dir).fit(Batch(None, None, train_md.iloc[:0]),
                                       unlabelled=Batch(X[tr], None, train_md))  # fmt: skip
            proba, n_nan = task_proba(m0, X[te])
            new.append(base | dict(row="pretrained_same_alignment", seed=-1,
                                   bal_acc=bal(y[te], proba), n_registry_nan=n_nan))  # fmt: skip
        rows += new
        if not subjects:
            pd.DataFrame(rows).to_csv(partial, index=False)
        log.info("finetune %s %s: %.0f s, %s", arm, subject, time.perf_counter() - t0,
                 [round(r["bal_acc"], 3) for r in new])  # fmt: skip
    if subjects:
        save(rows, RUNS_DIR / f"rerun_values_{arm}.csv")
    elif {r["subject"] for r in rows} >= set(targets):
        save(rows, out(f"values_{arm}.csv"))
        partial.unlink()


def part_check_b() -> None:
    """This fine-tuning path on arm B's models must give arm B's values (ex1_transfer_ah_sf)."""
    from sixthfinger.models.registry import Batch

    torch.set_num_threads(2)
    b = pd.read_csv(PATHS.summary / "ex1_transfer_ah_sf_values_B.csv")
    b = b[b.row == "finetuned"].set_index(["subject", "seed"]).bal_acc
    diffs = {}
    for subject in ("sub-01", "sub-02"):
        X, md = session_windows(subject)
        tr, te = split(md, CONFIG["train_runs"], CONFIG["test_runs"])
        y, train_md = md.label.to_numpy(), md.iloc[tr]
        for seed in SEEDS:
            m = ea_ft(B_MODELS).fit(Batch(X[tr], y[tr], train_md),
                                    unlabelled=Batch(X[tr], None, train_md), seed=seed)  # fmt: skip
            diffs[f"{subject} seed {seed}"] = abs(bal(y[te], task_proba(m, X[te])[0])
                                                  - b[(subject, seed)])  # fmt: skip
    update_checks(
        "finetune_path_reproduces_B", {"max_abs_diff": max(diffs.values()), "per_fit": diffs}
    )
    log.info("check B: %s", diffs)


def save(rows: list[dict], path: Path) -> None:
    from sixthfinger.paths import current_git_sha

    df = pd.DataFrame(rows)
    df["git_sha"] = current_git_sha()
    df.to_csv(path, index=False, float_format="%.6g")
    log.info("wrote %s (%d rows)", path.name, len(df))


def part_benchmark() -> None:
    from sklearn.metrics import balanced_accuracy_score

    import sixthfinger.models  # noqa: F401  (registers every method)
    from sixthfinger.evaluation.runner import method_params
    from sixthfinger.models.registry import Batch, make_method

    labels = pd.read_csv(DERIVED / "labels.csv")
    tasks = {
        "cylindrical_vs_spherical": [0, 1],
        "cylindrical_vs_lumbrical": [0, 2],
        "spherical_vs_lumbrical": [1, 2],
        "all_three": [0, 1, 2],
    }
    partial = RUNS_DIR / "benchmark.partial.csv"
    rows = pd.read_csv(partial).to_dict("records") if partial.exists() else []
    for person in GRASP_PEOPLE:
        if person in {r["person"] for r in rows}:
            continue
        lab = {
            d: labels[(labels.person == person) & (labels.day == d)].sort_values("trial")
            for d in ("day1", "day2")
        }
        X1 = np.load(DERIVED / f"{person}_day1.npy")
        X2 = np.load(DERIVED / f"{person}_day2.npy")
        y1, y2 = lab["day1"].label.to_numpy(), lab["day2"].label.to_numpy()
        for task, classes in tasks.items():
            te = np.flatnonzero(np.isin(y2, classes))
            for subset in ("all", "first40"):
                tr = np.flatnonzero(np.isin(y1, classes))
                if subset == "first40":
                    tr = np.sort(np.concatenate([tr[y1[tr] == c][:40] for c in classes]))
                for method in ("ts_lr", "csp_lda"):
                    params = method_params(method, PATHS.configs)
                    m = make_method(method, n_classes=len(classes), **params)
                    m.fit(Batch(X1[tr], y1[tr], pd.DataFrame({"trial": tr})))
                    pred = np.asarray(classes)[m.predict_proba(X2[te]).argmax(axis=1)]
                    rows.append(dict(person=person, task=task, train_set=subset, method=method,
                                     n_train=len(tr), n_test=len(te),
                                     bal_acc=balanced_accuracy_score(y2[te], pred),
                                     top_class_share=np.unique(pred, return_counts=True)[1].max()
                                     / len(te)))  # fmt: skip
        log.info("benchmark %s: %s", person,
                 {f"{r['task'][:11]}/{r['train_set']}/{r['method']}": round(r["bal_acc"], 3)
                  for r in rows if r["person"] == person})  # fmt: skip
        del X1, X2
        pd.DataFrame(rows).to_csv(partial, index=False)
    pd.DataFrame(rows).to_csv(out("benchmark.csv"), index=False, float_format="%.6g")
    partial.unlink()


def baselines() -> dict:
    """The committed T1 baselines and arm B of ex1_transfer_ah_sf, per patient."""
    from sixthfinger.evaluation.exploratory import t1_baselines

    s = PATHS.summary
    b = pd.read_csv(s / "ex1_transfer_ah_sf_values_B.csv")
    bc = pd.read_csv(s / "ex1_transfer_ah_sf_values_B_central.csv")
    return t1_baselines() | {
        "B": b[b.row == "finetuned"].groupby("subject").bal_acc.mean(),
        "B_pretrained_same_alignment": b[b.row == "pretrained_same_alignment"]
        .groupby("subject")
        .bal_acc.mean(),
        "B_central": bc[bc.row == "finetuned"].groupby("subject").bal_acc.mean(),
        "B_seeds": b[b.row == "finetuned"].set_index(["subject", "seed"]).bal_acc,
        "paired_old": pd.read_csv(s / "ex1_transfer_ah_sf_paired.csv").set_index("comparison"),
    }


def values(arm: str, row: str = "finetuned") -> pd.Series | None:
    path = out(f"values_{arm}.csv")
    if not path.exists():
        return None
    df = pd.read_csv(path)
    return df[df.row == row].groupby("subject").bal_acc.mean()


def primary_name() -> str:
    return "GP_vs_P" if len(p_targets()) == 22 else "GP_vs_B"


def comparisons() -> tuple[pd.DataFrame, dict]:
    from sixthfinger.evaluation.exploratory import paired_row as compare

    c = baselines()
    old = c["paired_old"]
    ids = c["B"].index

    def same(value: float, comparison: str, column: str) -> bool:
        """The arm-B summary keeps 6 significant digits: the recomputed mean must give them."""
        return float(f"{value:.6g}") == float(old.loc[comparison, column])

    checks = {
        "baseline patients": len(ids),
        "B mean (values_B.csv) equals paired.csv": same(c["B"].mean(), "B_vs_ts_lr", "arm_mean"),
        "ts_lr mean (rq1_subject_values.csv) equals paired.csv": same(
            c["ts_lr_pre"].reindex(ids).mean(), "B_vs_ts_lr", "base_mean"
        ),
        "eegnet_scratch mean (dl_baselines_subject_values.csv) equals paired.csv": same(
            c["eegnet_scratch_pre"].reindex(ids).mean(), "B", "base_mean"
        ),
        "B central mean (values_B_central.csv) equals paired.csv": same(
            c["B_central"].mean(), "B_vs_ts_lr [central_14]", "arm_mean"
        ),
        "ts_lr central mean (rq4_visual_cue_decode.csv) equals paired.csv": same(
            c["ts_lr_pre_central"].reindex(ids).mean(), "B_vs_ts_lr [central_14]", "base_mean"
        ),
        "B no fine-tuning mean (values_B.csv) equals paired.csv": same(
            c["B_pretrained_same_alignment"].mean(), "B_pretrained_same_alignment", "arm_mean"
        ),
        "baseline means": {
            "B": float(c["B"].mean()),
            "ts_lr": float(c["ts_lr_pre"].reindex(ids).mean()),
            "eegnet_scratch": float(c["eegnet_scratch_pre"].reindex(ids).mean()),
            "B_central": float(c["B_central"].mean()),
            "ts_lr_central": float(c["ts_lr_pre_central"].reindex(ids).mean()),
        },
    }
    rows = []
    arms = {a: values(a) for a in ARMS}
    gp, p, g, gc = arms["GP"], arms["P"], arms["G"], arms["GP_central"]
    if gp is not None:
        if p is not None and len(p) == 22:
            rows.append(compare("GP_vs_P", gp, p, "GP", "P"))
        gp0 = values("GP", "pretrained_same_alignment")
        rows += [
            compare("GP_vs_B", gp, c["B"], "GP", "B (eegnet_ea_ft)"),
            compare("GP_vs_ts_lr", gp, c["ts_lr_pre"], "GP", "ts_lr"),
            compare("GP_vs_eegnet_scratch", gp, c["eegnet_scratch_pre"], "GP", "eegnet_scratch"),
            compare("GP_no_finetune_vs_B_no_finetune", gp0, c["B_pretrained_same_alignment"],
                    "GP pre-trained, no fine-tuning", "B pre-trained, no fine-tuning"),
            compare("GP_vs_GP_no_finetune", gp, gp0, "GP", "GP pre-trained, no fine-tuning"),
        ]  # fmt: skip
        df = pd.read_csv(out("values_GP.csv"))
        ft = df[df.row == "finetuned"]
        checks["GP mean seed SD (points)"] = float(ft.groupby("subject").bal_acc.std().mean() * 100)
        checks["GP fine-tuned fits with registry NaN windows"] = int((ft.n_registry_nan > 0).sum())
    if g is not None:
        rows += [
            compare("G_vs_B", g, c["B"], "G", "B (eegnet_ea_ft)"),
            compare("G_vs_ts_lr", g, c["ts_lr_pre"], "G", "ts_lr"),
            compare("G_vs_eegnet_scratch", g, c["eegnet_scratch_pre"], "G", "eegnet_scratch"),
        ]
        if gp is not None:
            rows.append(compare("GP_vs_G", gp, g, "GP", "G"))
        df = pd.read_csv(out("values_G.csv"))
        checks["G mean seed SD (points)"] = float(
            df[df.row == "finetuned"].groupby("subject").bal_acc.std().mean() * 100
        )
    if p is not None:
        rows.append(compare("P_vs_B", p, c["B"].reindex(p.index), "P (re-run here)",
                            "B (models made on a Kaggle GPU)"))  # fmt: skip
        if gp is not None:
            rows.append(compare("GP_vs_P_on_P_targets", gp.reindex(p.index), p, "GP", "P"))
        df = pd.read_csv(out("values_P.csv"))
        per = df[df.row == "finetuned"].set_index(["subject", "seed"]).bal_acc
        bs = c["B_seeds"]
        checks["P minus B per target and seed (points)"] = {
            f"{s} seed {k}": round(float((per[(s, k)] - bs[(s, k)]) * 100), 2) for s, k in per.index
        }
        checks["P minus B per target, seed mean (points)"] = {
            s: round(float((p[s] - c["B"][s]) * 100), 2) for s in p.index
        }
        p0 = values("P", "pretrained_same_alignment")
        checks["P minus B per target, no fine-tuning (points)"] = {
            s: round(float((p0[s] - c["B_pretrained_same_alignment"][s]) * 100), 2)
            for s in p0.index
        }
    if gc is not None:
        rows += [
            compare("GP_central_vs_B_central", gc, c["B_central"], "GP, central 14 only",
                    "B, central 14 only"),
            compare("GP_central_vs_ts_lr_central", gc, c["ts_lr_pre_central"],
                    "GP, central 14 only", "ts_lr central"),
        ]  # fmt: skip
    return pd.DataFrame(rows), checks


def per_patient() -> pd.DataFrame:
    c = baselines()
    ids = c["B"].index
    cols = {
        "B": c["B"],
        "B_no_finetune": c["B_pretrained_same_alignment"],
        "ts_lr": c["ts_lr_pre"].reindex(ids),
        "eegnet_scratch": c["eegnet_scratch_pre"].reindex(ids),
    }
    for arm in ARMS:
        v = values(arm)
        if v is None:
            continue
        cols[arm] = v
        df = pd.read_csv(out(f"values_{arm}.csv"))
        cols[f"{arm}_seed_sd"] = df[df.row == "finetuned"].groupby("subject").bal_acc.std()
        if arm in ("GP", "P"):
            cols[f"{arm}_no_finetune"] = values(arm, "pretrained_same_alignment")
    cols["B_central"] = c["B_central"]
    cols["ts_lr_central"] = c["ts_lr_pre_central"].reindex(ids)
    # Pre-training on the same three validation patients: lower is a better fit to them.
    for arm, path in (("B", B_MODELS), ("GP", MODELS / "gp"), ("P", MODELS / "p")):
        if not (path / "manifest.json").exists():
            continue
        manifest = json.loads((path / "manifest.json").read_text())
        cols[f"{arm}_pretrain_valid_loss"] = pd.Series(
            {s: manifest[f"eegnet_loso_{s}_ea_raw.pt"]["best_valid_loss"] for s in ids
             if f"eegnet_loso_{s}_ea_raw.pt" in manifest}, dtype=float)  # fmt: skip
        cols[f"{arm}_pretrain_epochs"] = pd.Series(
            {s: manifest[f"eegnet_loso_{s}_ea_raw.pt"]["epochs_run"] for s in ids
             if f"eegnet_loso_{s}_ea_raw.pt" in manifest}, dtype=float)  # fmt: skip
    df = pd.DataFrame(cols).rename_axis("subject").reset_index()
    df.insert(1, "affected_side", df.subject.map(hemiplegia_side))
    return df


def benchmark_summary() -> pd.DataFrame:
    from sixthfinger.evaluation.metrics import chance_threshold

    b = pd.read_csv(out("benchmark.csv"))
    k = b.task.map(lambda t: 3 if t == "all_three" else 2)
    b["chance_threshold"] = [chance_threshold(n, c) for n, c in zip(b.n_test, k, strict=True)]
    b["above_chance"] = b.bal_acc > b.chance_threshold
    g = b.groupby(["task", "train_set", "method"])
    table = pd.DataFrame(
        {
            "n": g.size(),
            "mean": g.bal_acc.mean(),
            "sd": g.bal_acc.std(),
            "min": g.bal_acc.min(),
            "median": g.bal_acc.median(),
            "max": g.bal_acc.max(),
            "chance_threshold": g.chance_threshold.first(),
            "n_above_chance": g.above_chance.sum(),
        }
    )
    if "top_class_share" in b:
        table["n_one_class_only"] = g.top_class_share.apply(lambda v: int((v == 1).sum()))
    return table.reset_index()


def pretraining_table() -> pd.DataFrame:
    """One row per pre-trained model: this study's and arm B's."""
    rows = []
    for arm, path in (("B", B_MODELS), ("GP", MODELS / "gp"), ("P", MODELS / "p"),
                      ("G", MODELS / "g")):  # fmt: skip
        manifest = json.loads((path / "manifest.json").read_text())
        for name, e in sorted(manifest.items()):
            if arm == "B" and not name.endswith("_ea_raw.pt"):
                continue
            best = min(e["history"], key=lambda h: h["valid_loss"])
            rows.append(dict(arm=arm, model=name, target=e.get("target", ""), device=e["device"],
                             n_train_windows=e["n_train_windows"],
                             n_valid_windows=e["n_valid_windows"], epochs_run=e["epochs_run"],
                             best_epoch=e["best_epoch"], best_valid_loss=e["best_valid_loss"],
                             valid_acc_at_best=best["valid_acc"],
                             seconds=e["seconds"]))  # fmt: skip
    return pd.DataFrame(rows)


def part_summary() -> None:
    table, checks = comparisons()
    gp, b = values("GP"), baselines()["B"]
    if gp is not None:
        d = (gp - b).dropna() * 100
        checks["GP minus B per patient (points)"] = {
            "sd": float(d.std()),
            "min": float(d.min()),
            "max": float(d.max()),
            "patients_moved_10_or_more": int((d.abs() >= 10).sum()),
        }
        primary = table[table.comparison == primary_name()].diff_points.iloc[0]
        checks["central control"] = (
            "run"
            if values("GP_central") is not None
            else f"not run: {primary_name()} mean difference {primary:.2f} points, not above 0"
        )
    pre = pretraining_table()
    pre.to_csv(out("pretraining.csv"), index=False, float_format="%.6g")
    loss = pre[pre.arm.isin(["B", "GP", "P"])].pivot_table(
        index="target", columns="arm", values="best_valid_loss"
    )
    checks["best validation loss, same three validation patients"] = {
        "mean_B": float(loss.B.mean()),
        "mean_GP": float(loss.GP.mean()),
        "GP_higher_than_B": int((loss.GP > loss.B).sum()),
        "GP_lower_than_B": int((loss.GP < loss.B).sum()),
        "P_minus_B": {t: float(v) for t, v in (loss.P - loss.B).dropna().items()},
    }
    mine = pre[pre.arm != "B"]
    checks["pre-training hours on the device"] = (
        mine.groupby("arm").seconds.sum() / 3600
    ).to_dict()
    checks["disk GB"] = {
        str(d.relative_to(PATHS.root)): sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        / 1e9
        for d in (EXTERNAL, DERIVED, MODELS)
    }
    table.to_csv(out("paired.csv"), index=False, float_format="%.6g")
    per_patient().to_csv(out("per_patient.csv"), index=False, float_format="%.4g")
    update_checks("summary", checks)
    if out("benchmark.csv").exists():
        benchmark_summary().to_csv(out("benchmark_summary.csv"), index=False, float_format="%.4g")
    cols = ["comparison", "n", "arm_mean", "base_mean", "diff_points", "diff_ci_lo",
            "diff_ci_hi", "p_wilcoxon", "better", "worse", "tied", "diff_points_without_dev",
            "diff_ci_lo_without_dev", "diff_ci_hi_without_dev"]  # fmt: skip
    if len(table):
        with pd.option_context("display.width", 250, "display.max_columns", 30):
            log.info("\n%s", table[cols].round(4).to_string(index=False))
    log.info("checks: %s", checks)


VALUE_COLUMNS = ["arm", "subject", "session", "n_train", "n_test", "row", "seed", "bal_acc",
                 "n_registry_nan", "git_sha"]  # fmt: skip
CARRIED = {
    "values_GP.csv": VALUE_COLUMNS,
    "values_G.csv": VALUE_COLUMNS,
    "values_P.csv": VALUE_COLUMNS,
    "g_selection.csv": ["finetune_lr", "finetune_epochs", "mean_bal_acc", "tie_order", "chosen",
                        "mean_sub-01", "mean_sub-03"],
}  # fmt: skip
# The one-time checks a re-run would not repeat as they were: when the run started, the device
# timing that chose mps, and the projection that fixed P's three targets.
CARRIED_CHECKS = ["started", "device_timing", "projection"]


def part_carry(research: Path) -> None:
    """The expensive parts' per-fit values and one-time checks, with the commit that holds them."""
    from sixthfinger.evaluation.exploratory import carry, source_commit

    for name, columns in CARRIED.items():
        df = carry(research / name, out(name), columns)
        log.info("carried %s: %d rows, committed in %s", name, len(df), df.source_commit.iloc[0])
    # Every key keeps its place; the parts re-run here overwrite their own, the others stay.
    before = research / "checks.json"
    out("checks.json").write_text(before.read_text())
    log.info("carried checks.json (committed in %s); kept as carried: %s",
             source_commit(before), CARRIED_CHECKS)  # fmt: skip


def reconvert(person: str, day: str) -> dict:
    """One grasp person-day converted again in memory, against the cached windows."""
    X_uv, _, names, _ = read_grasp_mat(EXTERNAL / f"{person}_{day}.mat")
    win = imagery_window(convert_one(X_uv, names)[0])
    cached = np.load(DERIVED / f"{person}_{day}.npy")
    diff = float(np.abs(win - cached).max())
    return dict(file=f"{person}_{day}.npy", before="cached conversion", rows=len(win),
                rows_before=len(cached), columns=win.shape[1], missing_columns="",
                cells_differing=int((win != cached).sum()), max_abs_diff=diff,
                identical=diff == 0.0, note="converted again here")  # fmt: skip


def part_repro(research: Path, reconvert_ids: list[str]) -> None:
    from sixthfinger.evaluation.exploratory import (
        repro_table,
        settings_diff,
        source_commit,
        table_diff,
    )
    from sixthfinger.paths import current_git_sha

    names = ["values_GP.csv", "values_G.csv", "values_P.csv", "g_selection.csv", "benchmark.csv",
             "benchmark_summary.csv", "paired.csv", "per_patient.csv", "pretraining.csv",
             "checks.json"]  # fmt: skip
    parts = [repro_table(NAME, research, {n: out(n) for n in names})]
    for arm in ARMS:
        rerun = RUNS_DIR / f"rerun_values_{arm}.csv"
        if not rerun.exists():
            continue
        new = pd.read_csv(rerun)
        old = pd.read_csv(out(f"values_{arm}.csv"))
        old = old[old.subject.isin(new.subject)].reset_index(drop=True)
        res = table_diff(new, old)
        note = "re-run here for " + " ".join(new.subject.unique())
        parts.append(pd.DataFrame([dict(analysis=NAME, file=f"rerun of values_{arm}.csv",
                                        before=f"{NAME}_values_{arm}.csv", **res,
                                        note=note)]))  # fmt: skip
    parts.append(pd.DataFrame([dict(analysis=NAME, file="checks.json", before="checks.json",
                                    identical=None, note="carried, not re-run: "
                                    + ", ".join(CARRIED_CHECKS) + " (commit "
                                    + source_commit(research / "checks.json") + ")")]))  # fmt: skip
    for pid in reconvert_ids:
        person, day = pid.split("_")
        parts.append(pd.DataFrame([dict(analysis=NAME, **reconvert(person, day))]))
    before = json.loads((research / "config.json").read_text())
    parts.append(pd.DataFrame([dict(analysis=NAME, **settings_diff(CONFIG, before))]))
    table = pd.concat(parts, ignore_index=True)
    table["git_sha"] = current_git_sha()
    table.to_csv(out("repro.csv"), index=False, float_format="%.6g")
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        log.info("\n%s", table.drop(columns="note").to_string(index=False))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parts = ["fetch", "convert", "equivalence", "timing", "check_b", "benchmark", "pretrain_g",
             "select_g", "finetune", "pretrain_gp", "projection", "pretrain_p", "summary",
             "carry", "repro"]  # fmt: skip
    ap.add_argument("--part", required=True, choices=parts)
    ap.add_argument("--arm", choices=ARMS, help="finetune: which arm")
    ap.add_argument("--targets", nargs="+", default=None, help="pretrain_gp, pretrain_p")
    ap.add_argument("--subjects", nargs="+", default=None, help="finetune: re-run these")
    ap.add_argument("--device", default=None, help="pre-training device instead of the timed one")
    ap.add_argument("--research", type=Path, help="carry, repro: folder of the exploratory run")
    ap.add_argument("--reconvert", nargs="*", default=[], help="repro: e.g. S01_day1")
    args = ap.parse_args()
    if args.part in ("carry", "repro") and args.research is None:
        ap.error("--research is needed for carry and repro")
    if args.part == "finetune" and args.arm is None:
        ap.error("--arm is needed for finetune")
    if args.device:
        DEVICE_OVERRIDE.append(args.device)
    setup_logging()
    checks = out("checks.json")
    if args.part != "carry" and (
        not checks.exists() or "started" not in json.loads(checks.read_text())
    ):
        born = pd.Timestamp((RUNS_DIR / "run.log").stat().st_birthtime, unit="s", tz="UTC")
        update_checks("started", str(born.tz_convert("Asia/Kolkata").tz_localize(None)))
    t0 = time.perf_counter()
    log.info("part %s start", args.part)
    {
        "fetch": part_fetch,
        "convert": part_convert,
        "equivalence": part_equivalence,
        "timing": part_timing,
        "pretrain_gp": lambda: part_pretrain_patients(True, args.targets),
        "pretrain_p": lambda: part_pretrain_patients(False, args.targets or p_targets()),
        "pretrain_g": part_pretrain_g,
        "projection": part_projection,
        "select_g": part_select_g,
        "finetune": lambda: part_finetune(args.arm, args.subjects),
        "benchmark": part_benchmark,
        "summary": part_summary,
        "check_b": part_check_b,
        "carry": lambda: part_carry(args.research),
        "repro": lambda: part_repro(args.research, args.reconvert),
    }[args.part]()
    log.info("part %s done: %.0f s wall", args.part, time.perf_counter() - t0)


if __name__ == "__main__":
    main()
