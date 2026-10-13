"""The demo's model as a serverless function on the same site: one EEG window in, the
probabilities of rest, hand and sixth finger out.

GET  /api/decode  -> {"ok": true, "model": ..., "sha256": ...}
POST /api/decode  body: one window, float32 little-endian, channel-major (n_channels x
                  n_times, microvolts) -> {"probs": [...], "latency_ms": ...}

The page streams the recorded trials itself and sends each window here; if this fails it
decodes in the browser instead. A WebSocket server cannot run on Vercel, so this replaces
server/app (which streams too) on the live site; the model and preprocessing are the same.
"""

from __future__ import annotations

import hashlib
import json
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import numpy as np
import onnxruntime as ort

DEMO = Path(__file__).resolve().parent.parent / "public" / "demo"
MANIFEST = json.loads((DEMO / "manifest.json").read_text())
MODEL = MANIFEST["model"]
N_CH, N_T = int(MODEL["n_channels"]), int(MODEL["n_times"])
WINDOW_BYTES = N_CH * N_T * 4

_model_bytes = (DEMO / MODEL["file"]).read_bytes()
if hashlib.sha256(_model_bytes).hexdigest() != MODEL["sha256"]:
    raise RuntimeError("model.onnx does not match the manifest checksum")
_options = ort.SessionOptions()
_options.intra_op_num_threads = 1
_options.inter_op_num_threads = 1
SESSION = ort.InferenceSession(
    _model_bytes, sess_options=_options, providers=["CPUExecutionProvider"]
)


def preprocess(window_uv: np.ndarray) -> np.ndarray:
    """The manifest's preprocessing, as server/app/bundle.py apply_preprocessing does it."""
    x = window_uv.astype(np.float32, copy=True)
    for op in MANIFEST.get("preprocessing", []):
        if op["op"] == "scale":
            x *= np.float32(op.get("factor", 1.0))
        elif op["op"] == "spatial_filter":
            x = np.asarray(op["matrix"], dtype=np.float32) @ x
        elif op["op"] == "channel_standardize":
            mean = np.asarray(op["mean"], dtype=np.float32)[:, None]
            std = np.asarray(op["std"], dtype=np.float32)[:, None]
            x = (x - mean) / std
        else:
            raise ValueError(f"unknown preprocessing step {op['op']!r}")
    return x


def decode(body: bytes) -> dict:
    """Probabilities for one window, and how long the model took."""
    if len(body) != WINDOW_BYTES:
        raise ValueError(f"expected {WINDOW_BYTES} bytes ({N_CH} x {N_T} float32), got {len(body)}")
    window = np.frombuffer(body, dtype="<f4").reshape(N_CH, N_T)
    if not np.isfinite(window).all():
        raise ValueError("the window holds a value that is not a finite number")
    started = time.perf_counter()
    out = SESSION.run([MODEL["output_name"]], {MODEL["input_name"]: preprocess(window)[None]})[0][0]
    if MODEL["output"] == "logits":
        out = np.exp(out - out.max())
        out = out / out.sum()
    latency_ms = (time.perf_counter() - started) * 1000
    return {"probs": [float(p) for p in out], "latency_ms": round(latency_ms, 3)}


class handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self._send(200, {"ok": True, "model": MODEL["name"], "sha256": MODEL["sha256"]})

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length") or 0)
        if length != WINDOW_BYTES:
            self._send(400, {"error": f"expected {WINDOW_BYTES} bytes, got {length}"})
            return
        try:
            self._send(200, decode(self.rfile.read(length)))
        except ValueError as err:
            self._send(400, {"error": str(err)})
