import importlib.util

import numpy as np
import pytest

from sixthfinger.data.channels import CHANNELS_40, MIDLINE, mirror_permutation
from sixthfinger.paths import get_paths
from sixthfinger.preprocessing.alignment import align, reference_matrix


@pytest.fixture(scope="module")
def grasp():
    path = get_paths().root / "scripts" / "ex3_grasp_pretraining.py"
    spec = importlib.util.spec_from_file_location("ex3_grasp_pretraining", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mirroring_swaps_left_and_right_and_commutes_with_alignment(grasp):
    rng = np.random.default_rng(0)
    X = rng.standard_normal((6, 40, 200)).astype(np.float32) * 1e-5
    X[:, CHANNELS_40.index("C3")] *= 4  # a strong left motor channel
    perm = mirror_permutation()
    y = np.full(6, 3)
    plain = grasp.Windows([(X, np.arange(6), reference_matrix(X), None, y)], 1.0)
    mirrored = grasp.Windows([(X, np.arange(6), reference_matrix(X), perm, y)], 1.0)
    a, b = plain[0][0].numpy(), mirrored[0][0].numpy()
    c3, c4 = CHANNELS_40.index("C3"), CHANNELS_40.index("C4")
    assert np.array_equal(b[c4], a[c3]) and np.array_equal(b[c3], a[c4])
    for name in MIDLINE:
        assert np.array_equal(b[CHANNELS_40.index(name)], a[CHANNELS_40.index(name)])
    # Mirroring after the subject's alignment equals aligning the mirrored recording itself.
    Xm = X[:, perm]
    direct = align(Xm, reference_matrix(Xm))[0]
    assert np.abs(b - direct).max() < 1e-4 * np.abs(direct).max()


def test_each_window_is_scored_on_its_own_head(grasp):
    import torch

    logits = torch.tensor([[2.0, 0.5, 0.1, 9.0, 9.0, 9.0], [9.0, 9.0, 9.0, 0.2, 1.5, 0.3]])
    y = torch.tensor([0, 4])  # a patient's REST window, a healthy person's spherical grasp
    loss = grasp.HeadwiseCrossEntropy()(logits, y)
    ce = torch.nn.functional.cross_entropy
    expected = (ce(logits[:1, :3], torch.tensor([0])) + ce(logits[1:, 3:], torch.tensor([1]))) / 2
    assert loss.item() == pytest.approx(expected.item())
