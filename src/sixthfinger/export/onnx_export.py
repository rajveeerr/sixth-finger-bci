"""Export a trained decoder to ONNX and check it against PyTorch (P10 step 4.3).

The verified recipe of `06-VERIFIED-SNIPPETS.md` §8: braindecode's max-norm
parametrisations are removed first, the legacy exporter is used (`dynamo=False`, opset 18,
a dynamic batch axis), and a softmax is appended so the file outputs probabilities.
"""

from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import torch
from torch.nn.utils import parametrize

OPSET = 18


class WithSoftmax(torch.nn.Module):
    def __init__(self, net: torch.nn.Module):
        super().__init__()
        self.net = net

    def forward(self, x):
        return torch.softmax(self.net(x), dim=-1)


def own_classes(model: torch.nn.Module) -> torch.nn.Module:
    """Give each parametrised module of a copy its own class.

    torch gives a parametrised module a generated class, and `copy.deepcopy` keeps that class.
    Removing a parametrisation deletes a property from the class, which broke the original
    model after a deep copy was stripped (found in P10; the snippet of
    `06-VERIFIED-SNIPPETS.md` §8 never used the original again).
    """
    for module in model.modules():
        if parametrize.is_parametrized(module):
            cls = module.__class__
            body = {k: v for k, v in cls.__dict__.items() if k not in ("__dict__", "__weakref__")}
            module.__class__ = type(cls.__name__, cls.__bases__, body)
    return model


def strip_parametrizations(model: torch.nn.Module) -> torch.nn.Module:
    """Bake every parametrised weight (EEGNet's max-norm constraints) into a plain tensor."""
    for module in model.modules():
        if parametrize.is_parametrized(module):
            for name in list(module.parametrizations.keys()):
                parametrize.remove_parametrizations(module, name, leave_parametrized=True)
    return model


def export_onnx(
    module: torch.nn.Module,
    path: Path,
    n_chans: int,
    n_times: int,
    real: np.ndarray | None = None,
    seed: int = 0,
) -> dict:
    """Write `path` and return the parity of ONNX against PyTorch on random input and, if
    given, on real network inputs `real` (n, n_chans, n_times)."""
    import onnx
    import onnxruntime as ort

    copied = own_classes(copy.deepcopy(module).cpu().eval())
    plain = WithSoftmax(strip_parametrizations(copied)).eval()
    rng = np.random.default_rng(seed)
    x = (10 * rng.standard_normal((8, n_chans, n_times))).astype(np.float32)  # µV-sized
    torch.onnx.export(
        plain,
        (torch.from_numpy(x),),
        str(path),
        input_names=["eeg"],
        output_names=["probs"],
        opset_version=OPSET,
        dynamo=False,
        dynamic_axes={"eeg": {0: "batch"}, "probs": {0: "batch"}},
    )
    onnx.checker.check_model(onnx.load(str(path)))
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])

    def gap(inputs: np.ndarray) -> float:
        with torch.no_grad():
            ref = plain(torch.from_numpy(inputs)).numpy()
        return float(np.abs(session.run(None, {"eeg": inputs})[0] - ref).max())

    out = {"opset": OPSET, "bytes": Path(path).stat().st_size, "max_abs_diff_random": gap(x)}
    if real is not None:
        out["max_abs_diff_real"] = gap(np.ascontiguousarray(real, dtype=np.float32))
    return out


def onnx_probabilities(path: Path, inputs: np.ndarray, batch: int = 64) -> np.ndarray:
    """Run an exported model on network inputs (n, channels, times)."""
    import onnxruntime as ort

    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    x = np.ascontiguousarray(inputs, dtype=np.float32)
    return np.concatenate(
        [session.run(None, {"eeg": x[i : i + batch]})[0] for i in range(0, len(x), batch)]
    )
