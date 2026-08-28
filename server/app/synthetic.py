"""Synthetic EEG-like trials and a complete test bundle.

The real bundle is built from held-out dataset trials in phase P10. This one
exists so the server and the web app can be developed and tested without the
dataset. It is marked "synthetic" in its manifest and the web app says so on
screen.

Signal model: pink-ish background noise on all channels plus a 10 Hz mu rhythm
over the sensorimotor strip. During imagery the mu rhythm weakens (event-related
desynchronisation): over the left strip for affected-hand trials, over both
strips for sixth-finger trials.
"""

import argparse
import datetime as dt
import json
import shutil
from pathlib import Path

import numpy as np

SFREQ = 250.0
CHANNELS = [
    "AF3", "AF4", "Fz", "F1", "F2", "F3", "F4", "F5", "F6", "FCz",
    "FC1", "FC2", "FC3", "FC4", "FC5", "FC6", "Cz", "C1", "C2", "C3",
    "C4", "C5", "C6", "CP1", "CP2", "CP3", "CP4", "CP5", "CP6", "Pz",
    "P3", "P4", "P5", "P6", "POz", "PO3", "PO4", "PO5", "PO6", "CPz",
]  # fmt: skip
DISPLAY_CHANNELS = ["FC3", "C3", "CP3", "Cz", "FC4", "C4", "CP4"]
CLASSES = [
    {"id": 0, "name": "rest", "label": "Rest", "command": "IDLE"},
    {"id": 1, "name": "affected_hand", "label": "Affected hand", "command": "HAND_GRASP"},
    {"id": 2, "name": "sixth_finger", "label": "Sixth finger", "command": "SIXTH_FINGER_FLEX"},
]

LEFT = {"C3": 1.0, "C1": 0.7, "C5": 0.7, "CP3": 0.6, "FC3": 0.6, "CP1": 0.4, "FC1": 0.4}
RIGHT = {"C4": 1.0, "C2": 0.7, "C6": 0.7, "CP4": 0.6, "FC4": 0.6, "CP2": 0.4, "FC2": 0.4}
MIDLINE = {"Cz": 0.6, "FCz": 0.4, "CPz": 0.4}
ERD = {1: {"left": 0.25, "right": 0.9, "mid": 0.7}, 2: {"left": 0.35, "right": 0.35, "mid": 0.3}}


def _weights(group: dict[str, float]) -> np.ndarray:
    w = np.zeros(len(CHANNELS))
    for name, value in group.items():
        w[CHANNELS.index(name)] = value
    return w


def make_trial(rng: np.random.Generator, label: int) -> tuple[np.ndarray, float]:
    """One trial from rest onset to 6 s after the cue: ((40, n) microvolts, cue onset in s)."""
    cue_s = 8.0 + float(rng.uniform(0.0, 0.6))
    n = round((cue_s + 6.0) * SFREQ)
    t = np.arange(n) / SFREQ

    white = rng.normal(0.0, 1.0, (len(CHANNELS), n))
    background = np.zeros_like(white)
    for i in range(1, n):
        background[:, i] = 0.95 * background[:, i - 1] + white[:, i]
    background = 0.6 * background / background.std(axis=1, keepdims=True)
    background += rng.normal(0.0, 0.5, background.shape)

    freq = float(rng.uniform(9.0, 11.0))
    phase = rng.uniform(0, 2 * np.pi)
    envelope = 1.0 + 0.15 * np.sin(2 * np.pi * 0.3 * t + rng.uniform(0, 2 * np.pi))
    mu = 3.0 * envelope * np.sin(2 * np.pi * freq * t + phase)

    ramp = np.clip((t - cue_s - 0.3) / 0.5, 0.0, 1.0)
    signal = background
    for side, group in (("left", LEFT), ("right", RIGHT), ("mid", MIDLINE)):
        depth = ERD.get(label, {}).get(side, 1.0)
        gain = 1.0 - (1.0 - depth) * ramp
        signal = signal + _weights(group)[:, None] * (mu * gain)[None, :]
    return signal.astype(np.float32), round(cue_s, 3)


def make_windows(rng: np.random.Generator, n_trials: int) -> tuple[np.ndarray, np.ndarray]:
    """Training windows cut exactly like the real pipeline: [1, 5) s after rest and cue onsets."""
    xs, ys = [], []
    for i in range(n_trials):
        label = 1 + i % 2
        data, cue_s = make_trial(rng, label)
        cue = round(cue_s * SFREQ)
        xs.append(data[:, 250:1250])
        ys.append(0)
        xs.append(data[:, cue + 250 : cue + 1250])
        ys.append(label)
    return np.stack(xs), np.asarray(ys)


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_bundle(
    out: Path, model: Path, n_trials: int = 6, seed: int = 7, dtype: str = "int16"
) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    scale_uv = 0.01 if dtype == "int16" else 1.0

    trials, blobs, offset = [], [], 0
    for i in range(n_trials):
        label = 1 + i % 2
        data, cue_s = make_trial(rng, label)
        encoded = (
            np.clip(np.round(data / scale_uv), -32768, 32767).astype("<i2")
            if dtype == "int16"
            else data.astype("<f4")
        )
        blobs.append(encoded.tobytes(order="C"))
        trials.append(
            {
                "index": i,
                "uid": f"synthetic_trial-{i + 1:02d}",
                "label": label,
                "cue_onset_s": cue_s,
                "n_samples": int(data.shape[1]),
                "offset_bytes": offset,
            }
        )
        offset += len(blobs[-1])

    trials_path = out / "trials.bin"
    trials_path.write_bytes(b"".join(blobs))
    model_path = out / "model.onnx"
    if model.resolve() != model_path.resolve():
        shutil.copyfile(model, model_path)

    manifest = {
        "schema_version": 1,
        "created_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "synthetic": True,
        "source": {
            "dataset": "Synthetic test signals (not EEG)",
            "doi": "",
            "license": "CC0-1.0",
            "subject": "synthetic",
            "session": "none",
            "runs": [],
            "attribution": "Generated by server/app/synthetic.py for testing only.",
        },
        "sfreq": SFREQ,
        "channels": CHANNELS,
        "display_channels": DISPLAY_CHANNELS,
        "display_decimation": 2,
        "units": "uV",
        "classes": CLASSES,
        "window": {"start_s": 1.0, "end_s": 5.0},
        "model": {
            "file": "model.onnx",
            "sha256": _sha256(model_path),
            "input_name": "eeg",
            "output_name": "probs",
            "output": "probabilities",
            "n_channels": len(CHANNELS),
            "n_times": 1000,
            "name": "EEGNet test model",
            "method": "eegnet_synthetic_fixture",
            "trained_on": "synthetic signals from server/app/synthetic.py",
            "notes": "Test fixture. Not trained on brain data.",
        },
        "preprocessing": [{"op": "scale", "factor": 1.0}],
        "encoding": {"dtype": dtype, "scale_uv": scale_uv},
        "trials_file": "trials.bin",
        "trials_sha256": _sha256(trials_path),
        "predictions_file": "predictions.json",
        "trials": trials,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    write_predictions(out)
    return out


def write_predictions(bundle_dir: Path) -> None:
    """Precompute trial-mode predictions so the web app can replay them offline."""
    from .bundle import Bundle
    from .inference import Decoder

    bundle = Bundle(bundle_dir)
    decoder = Decoder(bundle)
    m = bundle.manifest
    w0, w1 = round(m.window.start_s * m.sfreq), round(m.window.end_s * m.sfreq)
    items = []
    for info in m.trials:
        data = bundle.trial_data(info.index)
        cue = round(info.cue_onset_s * m.sfreq)
        for window, start in (("rest", 0), ("imagery", cue)):
            probs, _ = decoder.predict(data[:, start + w0 : start + w1])
            items.append(
                {
                    "trial": info.index,
                    "window": window,
                    "probs": [round(float(p), 5) for p in probs],
                    "label_id": int(np.argmax(probs)),
                }
            )
    payload = {"schema_version": 1, "model_sha256": m.model.sha256, "items": items}
    (bundle_dir / m.predictions_file).write_text(json.dumps(payload, indent=1) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Write a synthetic demo bundle.")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--model",
        type=Path,
        default=Path(__file__).parent.parent / "tests" / "fixtures" / "test_model.onnx",
    )
    parser.add_argument("--trials", type=int, default=6)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--dtype", choices=["int16", "float32"], default="int16")
    args = parser.parse_args()
    path = build_bundle(args.out, args.model, args.trials, args.seed, args.dtype)
    print(f"wrote synthetic bundle to {path}")


if __name__ == "__main__":
    main()
