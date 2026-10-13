"""The live site's model function (web/api/decode.py) decodes like the browser and the server."""

import importlib.util
import json

import numpy as np
import pytest

from sixthfinger.paths import get_paths

ROOT = get_paths().root
DEMO = ROOT / "web" / "public" / "demo"


@pytest.fixture(scope="module")
def api():
    spec = importlib.util.spec_from_file_location(
        "web_api_decode", ROOT / "web" / "api" / "decode.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def first_rest_window(manifest: dict) -> np.ndarray:
    """The rest window of the first trial in microvolts, cut as server/app/stream.py does."""
    trial = manifest["trials"][0]
    enc = manifest["encoding"]
    raw = np.fromfile(DEMO / manifest["trials_file"], dtype=enc["dtype"])
    n_ch = len(manifest["channels"])
    start = trial["offset_bytes"] // np.dtype(enc["dtype"]).itemsize
    data = raw[start : start + n_ch * trial["n_samples"]].reshape(n_ch, trial["n_samples"])
    sfreq = manifest["sfreq"]
    w0, w1 = (
        round(manifest["window"]["start_s"] * sfreq),
        round(manifest["window"]["end_s"] * sfreq),
    )
    return (data[:, w0:w1].astype(np.float32) * np.float32(enc["scale_uv"])).astype("<f4")


def test_decodes_a_bundle_window_as_stored(api):
    manifest = json.loads((DEMO / "manifest.json").read_text())
    stored = json.loads((DEMO / manifest["predictions_file"]).read_text())["items"]
    expected = next(p for p in stored if p["trial"] == 0 and p["window"] == "rest")
    out = api.decode(first_rest_window(manifest).tobytes())
    assert len(out["probs"]) == len(manifest["classes"])
    assert out["probs"] == pytest.approx(expected["probs"], abs=1e-4)


def test_refuses_a_window_of_the_wrong_size_or_with_nan(api):
    with pytest.raises(ValueError):
        api.decode(b"\x00" * 12)
    bad = np.zeros((api.N_CH, api.N_T), dtype="<f4")
    bad[0, 0] = np.nan
    with pytest.raises(ValueError):
        api.decode(bad.tobytes())
