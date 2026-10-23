"""Time how long the demo's model takes to decide one 4 s window (a new measurement, P14).

uv run python scripts/time_demo_inference.py

The deployed bundle (web/public/demo/) is loaded with the server's own Bundle and Decoder
(server/app/bundle.py and inference.py): onnxruntime on the CPU with one thread, the
manifest's preprocessing, and the latency `Decoder.predict` reports, which covers the
preprocessing, the model and the softmax. The windows are every 4 s window inside a stored
trial that ends on the continuous mode's 0.5 s hop, decided once per pass after a short
untimed warm-up. Before timing, the decoder's answers on the trial-mode windows are checked
against the stored predictions.json, so the model and preprocessing are the deployed ones.

Writes results/summary/demo_inference_timing.json (median, quartiles, n, the machine) and
demo_inference_timing.csv (every timed window). The figure quoted in P10 was timed once by
hand with no samples kept; this file replaces it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import subprocess
import sys

import numpy as np
import pandas as pd

from sixthfinger.paths import current_git_sha, get_paths

HOP_S = 0.5  # the continuous mode's hop (server/app/stream.py)
OUT = "demo_inference_timing"


def server_modules():
    """The server's bundle and inference modules; server/ is not installed in this env."""
    sys.path.insert(0, str(get_paths().root / "server"))
    from app import bundle, inference

    return bundle, inference


def sysctl(name: str) -> str | None:
    try:
        out = subprocess.run(["sysctl", "-n", name], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip()


def machine() -> dict:
    import onnxruntime as ort

    cpu = sysctl("machdep.cpu.brand_string") or platform.processor()
    memory = sysctl("hw.memsize")
    darwin = platform.system() == "Darwin"
    return {
        "cpu": cpu,
        "memory_gb": round(int(memory) / 2**30) if memory else None,
        "os": f"macOS {platform.mac_ver()[0]}" if darwin else platform.platform(),
        "python": platform.python_version(),
        "onnxruntime": ort.__version__,
        "numpy": np.__version__,
        "provider": "CPUExecutionProvider",
        "intra_op_threads": 1,
    }


def stored_parity(bundle, decoder) -> float:
    """Largest difference from predictions.json on the trial-mode windows."""
    window = bundle.manifest.window
    sfreq = bundle.manifest.sfreq
    w0, w1 = round(window.start_s * sfreq), round(window.end_s * sfreq)
    gap = 0.0
    for item in bundle.predictions["items"]:
        info = bundle.manifest.trials[item["trial"]]
        data = bundle.trial_data(item["trial"])
        start = 0 if item["window"] == "rest" else round(info.cue_onset_s * sfreq)
        probs, _ = decoder.predict(data[:, start + w0 : start + w1])
        gap = max(gap, float(np.abs(probs - np.asarray(item["probs"])).max()))
    return gap


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--passes", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=20)
    args = parser.parse_args()

    paths = get_paths()
    demo = paths.root / "web" / "public" / "demo"
    bundle_mod, inference = server_modules()
    bundle = bundle_mod.Bundle(demo)
    decoder = inference.Decoder(bundle)
    n_times, hop = decoder.n_times, round(HOP_S * bundle.manifest.sfreq)

    # The stored predictions are rounded to 5 decimals.
    parity = stored_parity(bundle, decoder)
    if parity > 1e-4:
        raise SystemExit(f"the decoder differs from predictions.json by {parity:.2g}")

    trials = [bundle.trial_data(i) for i in range(bundle.n_trials)]
    windows = [
        (i, end)
        for i, info in enumerate(bundle.manifest.trials)
        for end in range(n_times, info.n_samples + 1, hop)
    ]
    for i, end in windows[: args.warmup]:
        decoder.predict(trials[i][:, end - n_times : end])

    load_before = os.getloadavg()[0]
    started = dt.datetime.now(dt.UTC)
    rows = []
    for p in range(args.passes):
        for i, end in windows:
            _, ms = decoder.predict(trials[i][:, end - n_times : end])
            rows.append({"pass": p, "trial": i, "end_sample": end, "latency_ms": ms})
    load_after = os.getloadavg()[0]

    times = pd.DataFrame(rows)
    ms = times.latency_ms.to_numpy()
    q1, median, q3 = np.percentile(ms, [25, 50, 75])
    result = {
        "what": (
            "wall-clock time of the server's Decoder.predict on one 4 s window of the stored "
            "demo recording: preprocessing, onnxruntime and softmax (ms)"
        ),
        "new_measurement": (
            "measured for P14 on the date below, not a summary of an earlier run; the P10 "
            "figure was timed once by hand with no samples kept"
        ),
        "measured_at": started.isoformat(timespec="seconds"),
        "git_sha": current_git_sha(),
        "model": {"file": "web/public/demo/model.onnx", "sha256": bundle.manifest.model.sha256},
        "windows": {
            "definition": (
                "every 4 s window inside a stored trial ending on the continuous mode's 0.5 s "
                "hop, decided once per pass"
            ),
            "trials": bundle.n_trials,
            "per_pass": len(windows),
            "passes": args.passes,
            "warmup_untimed": args.warmup,
        },
        "n": len(ms),
        "latency_ms": {
            "median": round(float(median), 4),
            "q1": round(float(q1), 4),
            "q3": round(float(q3), 4),
            "iqr": round(float(q3 - q1), 4),
            "min": round(float(ms.min()), 4),
            "max": round(float(ms.max()), 4),
        },
        "stored_predictions_max_abs_diff": parity,
        "machine": machine(),
        "load_average_1min": {"before": round(load_before, 2), "after": round(load_after, 2)},
    }
    summary = paths.root / "results" / "summary"
    (summary / f"{OUT}.json").write_text(json.dumps(result, indent=1) + "\n")
    times.to_csv(summary / f"{OUT}.csv", index=False, float_format="%.4f")
    print(json.dumps(result["latency_ms"]), "n =", result["n"], "on", result["machine"]["cpu"])


if __name__ == "__main__":
    main()
