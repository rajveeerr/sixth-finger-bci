import numpy as np

from sixthfinger.config import load_data_config
from sixthfinger.data.channels import (
    CHANNELS_40,
    LEFT_HEMIPLEGIC,
    MIDLINE,
    MIRROR_PAIRS,
    hemiplegia_side,
    mirror_if_needed,
    mirror_permutation,
    subject_group,
)


def test_forty_unique_channels():
    assert len(CHANNELS_40) == 40
    assert len(set(CHANNELS_40)) == 40


def test_constants_match_config():
    cfg = load_data_config()
    assert tuple(cfg.channels.keep) == CHANNELS_40
    assert {tuple(p) for p in cfg.channels.mirror_pairs} == set(MIRROR_PAIRS)
    assert set(cfg.subjects.left_hemiplegic) == LEFT_HEMIPLEGIC


def test_every_lateral_channel_has_a_partner():
    paired = {c for pair in MIRROR_PAIRS for c in pair}
    assert paired | set(MIDLINE) == set(CHANNELS_40)


def test_mirror_is_an_involution():
    perm = mirror_permutation()
    assert np.array_equal(perm[perm], np.arange(40))


def test_mirror_swaps_c3_c4_and_keeps_cz():
    x = np.arange(40, dtype=float)[None, :, None].repeat(3, axis=2)
    out = mirror_if_needed(x, "sub-03")
    c3, c4, cz = (CHANNELS_40.index(c) for c in ("C3", "C4", "Cz"))
    assert out[0, c3, 0] == c4
    assert out[0, c4, 0] == c3
    assert out[0, cz, 0] == cz


def test_right_hemiplegic_untouched():
    x = np.random.default_rng(0).standard_normal((2, 40, 5))
    assert mirror_if_needed(x, "sub-01") is x


def test_subject_metadata():
    assert hemiplegia_side("sub-03") == "L"
    assert hemiplegia_side("sub-01") == "R"
    assert subject_group("sub-01") == "B"
    assert subject_group("sub-07") == "T"
