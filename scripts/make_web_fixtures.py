"""Fixtures for the web unit tests, made by the server's own Python code (P11 step 4.1).

uv run python scripts/make_web_fixtures.py

web/src/stream/__fixtures__/bundle.json: the first samples of the real bundle's first trial
as server/app/bundle.py reads them, and apply_preprocessing on a small window with every
operation, so the TypeScript port is checked against the Python reference.
"""

from __future__ import annotations

import json

import numpy as np

from sixthfinger.export.demo_bundle import server_module
from sixthfinger.paths import get_paths


def main() -> None:
    root = get_paths().root
    bundle_mod = server_module("bundle")
    bundle = bundle_mod.Bundle(root / "web" / "public" / "demo")
    first = bundle.trial_data(0)
    rng = np.random.default_rng(0)
    window = rng.normal(0, 20, (3, 8)).astype(np.float32)
    ops = [
        {"op": "scale", "factor": 0.5},
        {"op": "spatial_filter", "matrix": rng.normal(0, 1, (3, 3)).round(4).tolist()},
        {"op": "channel_standardize", "mean": [0.1, -0.2, 0.3], "std": [1.5, 2.0, 0.5]},
    ]
    parsed = [bundle_mod.PreprocessOp(**op) for op in ops]
    out = bundle_mod.apply_preprocessing(window, parsed)
    fixture = {
        "n_trials": bundle.n_trials,
        "trial0_shape": list(first.shape),
        "trial0_head": first[:3, :5].round(4).tolist(),
        "window": window.tolist(),
        "ops": ops,
        "preprocessed": out.tolist(),
    }
    path = root / "web" / "src" / "stream" / "__fixtures__" / "bundle.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(fixture, indent=1) + "\n")
    print(path)


if __name__ == "__main__":
    main()
