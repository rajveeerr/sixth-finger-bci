"""Count EEGNet's trainable weights as the study builds it, and the numbers in the demo's ONNX file.

uv run python scripts/count_eegnet_weights.py

The network comes from the study's own factory (`models.deep.build_module`) with the
pre-registered settings of configs/models/eegnet_scratch.yaml and eegnet_ea_ft.yaml, for the
data config's 40 channels and 4 s windows and the three classes of T2; a two-class network
(T1, T3) is counted as well. The deployed model (web/public/demo/model.onnx) is counted the
way results/summary/demo_page.json counts it: every number stored in the graph's
initializers. Writes results/summary/eegnet_weights.json, with the reason when the counts
differ.
"""

from __future__ import annotations

import json

import numpy as np
import onnx
import torch

from sixthfinger.config import load_data_config, load_protocol_config
from sixthfinger.evaluation.runner import method_params
from sixthfinger.models.deep import build_module
from sixthfinger.paths import current_git_sha, get_paths

METHODS = ("eegnet_scratch", "eegnet_ea_ft")


def trainable(net: torch.nn.Module) -> int:
    return sum(p.numel() for p in net.parameters() if p.requires_grad)


def study_model(n_chans: int, n_classes: int, n_times: int) -> dict:
    paths = get_paths()
    nets = {
        m: build_module(method_params(m, paths.configs), n_chans, n_classes, n_times)
        for m in METHODS
    }
    counts = {m: trainable(net) for m, net in nets.items()}
    if len(set(counts.values())) != 1:
        raise SystemExit(f"the two EEGNet methods build different networks: {counts}")
    net = nets[METHODS[0]]
    norms = {
        name: module.num_features
        for name, module in net.named_modules()
        if isinstance(module, torch.nn.BatchNorm2d)
    }
    layers: dict[str, int] = {}
    for name, p in net.named_parameters():
        if p.requires_grad:
            layer = name.split(".parametrizations")[0].rsplit(".", 1)[0]
            layers[layer] = layers.get(layer, 0) + p.numel()
    return {
        "trainable": counts[METHODS[0]],
        "per_layer": layers,
        "batch_norm_channels": norms,
        "batch_norm_trainable": 2 * sum(norms.values()),
        "batch_norm_running_statistics": 2 * sum(norms.values()),
    }


def onnx_model(path) -> dict:
    model = onnx.load(path)
    sizes = {t.name: int(np.prod(t.dims)) for t in model.graph.initializer}
    shape = lambda v: [d.dim_value or d.dim_param for d in v.type.tensor_type.shape.dim]  # noqa: E731
    return {
        "numbers": sum(sizes.values()),
        "initializers": sizes,
        "operators": sorted({node.op_type for node in model.graph.node}),
        "input": shape(model.graph.input[0]),
        "output": shape(model.graph.output[0]),
    }


def main() -> None:
    paths = get_paths()
    data_cfg, proto = load_data_config(), load_protocol_config()
    n_chans, n_times = len(data_cfg.channels.keep), data_cfg.n_times
    n_classes = len(proto.tasks["T2_rest_ah_sf"])
    study = study_model(n_chans, n_classes, n_times)
    two_class = study_model(n_chans, len(proto.tasks["T3_sf_vs_rest"]), n_times)["trainable"]
    deployed = onnx_model(paths.root / "web" / "public" / "demo" / "model.onnx")
    if deployed["input"][1:] != [n_chans, n_times] or deployed["output"][1:] != [n_classes]:
        raise SystemExit(f"the ONNX model is not the study's network: {deployed['input']}")
    page = json.loads((paths.root / "results" / "summary" / "demo_page.json").read_text())

    # Exported in eval mode, each batch normalisation is folded into the convolution before
    # it: its scale and shift (two numbers per channel) become one bias per channel.
    folded = (
        study["trainable"]
        - study["batch_norm_trainable"]
        + sum(study["batch_norm_channels"].values())
    )
    explained = folded == deployed["numbers"] and "BatchNormalization" not in deployed["operators"]
    if deployed["numbers"] == study["trainable"]:
        reason = "the two counts are equal"
    elif explained:
        reason = (
            "the export folds each of the three batch normalisations into the convolution "
            "before it (the ONNX graph has no BatchNormalization node): their scale and shift, "
            "two trainable numbers per channel, and their running mean and variance become one "
            "bias per channel of that convolution, so the file holds the trainable weights "
            "minus one number per batch-normalised channel"
        )
    else:
        raise SystemExit(f"unexplained difference: {study['trainable']} vs {deployed['numbers']}")
    result = {
        "what": (
            "EEGNet's trainable weights as the study builds it, and the numbers stored in "
            "the demo's ONNX model"
        ),
        "git_sha": current_git_sha(),
        "study_model": {
            "factory": "sixthfinger.models.deep.build_module",
            "configs": [f"configs/models/{m}.yaml" for m in METHODS],
            "channels": n_chans,
            "classes": n_classes,
            "samples": n_times,
            "sfreq": data_cfg.signal.sfreq,
        }
        | study,
        "two_class_trainable": two_class,
        "deployed_onnx": {"file": "web/public/demo/model.onnx"} | deployed,
        "difference": study["trainable"] - deployed["numbers"],
        "onnx_equals_demo_parameters": deployed["numbers"] == page["parameters"],
        "reason": reason,
    }
    out = paths.root / "results" / "summary" / "eegnet_weights.json"
    out.write_text(json.dumps(result, indent=1) + "\n")
    print(f"trainable {study['trainable']}, ONNX {deployed['numbers']}: {reason}")


if __name__ == "__main__":
    main()
