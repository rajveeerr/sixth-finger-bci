import time

import numpy as np
import onnxruntime as ort

from .bundle import Bundle, apply_preprocessing


def softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=-1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=-1, keepdims=True)


class Decoder:
    """Runs the exported model on one window at a time."""

    def __init__(self, bundle: Bundle) -> None:
        info = bundle.manifest.model
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self._session = ort.InferenceSession(
            str(bundle.model_path), sess_options=options, providers=["CPUExecutionProvider"]
        )
        self._input = info.input_name
        self._output = info.output_name
        self._returns_logits = info.output == "logits"
        self._ops = bundle.manifest.preprocessing
        self.n_channels = info.n_channels
        self.n_times = info.n_times

    def predict(self, window_uv: np.ndarray) -> tuple[np.ndarray, float]:
        """Class probabilities for a (n_channels, n_times) window, and latency in ms."""
        if window_uv.shape != (self.n_channels, self.n_times):
            raise ValueError(
                f"expected window {(self.n_channels, self.n_times)}, got {window_uv.shape}"
            )
        started = time.perf_counter()
        x = apply_preprocessing(window_uv, self._ops)[None]
        out = self._session.run([self._output], {self._input: x})[0][0]
        probs = softmax(out) if self._returns_logits else out
        latency_ms = (time.perf_counter() - started) * 1000
        return probs.astype(np.float64), latency_ms
