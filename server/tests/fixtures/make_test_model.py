"""Rebuild test_model.onnx: a small EEGNet trained on synthetic signals.

Needs PyTorch and braindecode, which the server itself does not depend on:

    uv run --no-project --python 3.12 --with torch==2.14.1 --with braindecode==1.8.1 \
        --with onnx==1.23.1 --with onnxscript --with onnxruntime==1.30.0 \
        python server/tests/fixtures/make_test_model.py

The export steps are the same ones the real model goes through in phase P10.
"""

import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
from braindecode.models import EEGNet
from torch import nn
from torch.nn.utils import parametrize

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from app.synthetic import CHANNELS, make_windows  # noqa: E402


class WithSoftmax(nn.Module):
    def __init__(self, model: nn.Module) -> None:
        super().__init__()
        self.model = model

    def forward(self, eeg: torch.Tensor) -> torch.Tensor:
        return torch.softmax(self.model(eeg), dim=-1)


def strip_parametrizations(model: nn.Module) -> nn.Module:
    # EEGNet's max-norm constraint is a parametrization that calls aten::renorm,
    # which neither ONNX exporter supports. Baking it in leaves the outputs unchanged.
    for module in model.modules():
        if parametrize.is_parametrized(module):
            for name in list(module.parametrizations.keys()):
                parametrize.remove_parametrizations(module, name, leave_parametrized=True)
    return model


def main() -> None:
    torch.manual_seed(0)
    rng = np.random.default_rng(0)
    x_train, y_train = make_windows(rng, 160)
    x_test, y_test = make_windows(np.random.default_rng(1), 40)

    model = EEGNet(n_chans=len(CHANNELS), n_outputs=3, n_times=1000, sfreq=250)
    optimiser = torch.optim.Adam(model.parameters(), lr=3e-3)
    loss_fn = nn.CrossEntropyLoss()
    xt, yt = torch.from_numpy(x_train), torch.from_numpy(y_train)
    for epoch in range(40):
        model.train()
        order = torch.randperm(len(xt))
        for batch in order.split(32):
            optimiser.zero_grad()
            loss = loss_fn(model(xt[batch]), yt[batch])
            loss.backward()
            optimiser.step()
        if epoch % 10 == 9:
            print(f"epoch {epoch + 1} loss {loss.item():.3f}")

    model.eval()
    with torch.no_grad():
        accuracy = (model(torch.from_numpy(x_test)).argmax(1).numpy() == y_test).mean()
    print(f"accuracy on fresh synthetic windows: {accuracy:.3f}")

    export = WithSoftmax(strip_parametrizations(model)).eval()
    path = HERE / "test_model.onnx"
    torch.onnx.export(
        export,
        (torch.from_numpy(x_test[:2]),),
        str(path),
        input_names=["eeg"],
        output_names=["probs"],
        opset_version=18,
        dynamo=True,
        external_data=False,
        dynamic_shapes=({0: torch.export.Dim("batch", min=1, max=256)},),
    )
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    onnx_probs = session.run(None, {"eeg": x_test[:8]})[0]
    with torch.no_grad():
        torch_probs = export(torch.from_numpy(x_test[:8])).numpy()
    print(f"max |torch - onnx| = {np.abs(onnx_probs - torch_probs).max():.2e}")
    print(f"wrote {path} ({path.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
