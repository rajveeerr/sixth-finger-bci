"""Channel set, hemisphere mirroring and subject metadata used across the project."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

# The 40 analysis channels, in the order of the dataset's electrodes.tsv.
CHANNELS_40: tuple[str, ...] = (
    "AF3", "AF4", "Fz", "F1", "F2", "F3", "F4", "F5", "F6",
    "FCz", "FC1", "FC2", "FC3", "FC4", "FC5", "FC6",
    "Cz", "C1", "C2", "C3", "C4", "C5", "C6",
    "CP1", "CP2", "CP3", "CP4", "CP5", "CP6",
    "Pz", "P3", "P4", "P5", "P6",
    "POz", "PO3", "PO4", "PO5", "PO6",
    "CPz",
)  # fmt: skip

# The preprocessed files still carry these frontal-pole channels; the authors drop them.
DROPPED_CHANNELS: tuple[str, ...] = ("Fpz", "Fp1", "Fp2")

# Left/right homologues (odd number = left hemisphere in the 10-20 system).
MIRROR_PAIRS: tuple[tuple[str, str], ...] = (
    ("AF3", "AF4"), ("F1", "F2"), ("F3", "F4"), ("F5", "F6"),
    ("FC1", "FC2"), ("FC3", "FC4"), ("FC5", "FC6"),
    ("C1", "C2"), ("C3", "C4"), ("C5", "C6"),
    ("CP1", "CP2"), ("CP3", "CP4"), ("CP5", "CP6"),
    ("P3", "P4"), ("P5", "P6"), ("PO3", "PO4"), ("PO5", "PO6"),
)  # fmt: skip

MIDLINE: tuple[str, ...] = ("Fz", "FCz", "Cz", "CPz", "Pz", "POz")

LEFT_HEMIPLEGIC: frozenset[str] = frozenset(
    {"sub-03", "sub-04", "sub-05", "sub-09", "sub-11", "sub-12", "sub-17", "sub-18", "sub-24"}
)

BCI_GROUP: frozenset[str] = frozenset(
    f"sub-{n:02d}" for n in (1, 2, 3, 4, 5, 6, 9, 10, 12, 15, 16, 18, 20, 23)
)


def subject_group(subject: str) -> str:
    """'B' for the BCI-training group, 'T' for conventional therapy."""
    return "B" if subject in BCI_GROUP else "T"


def hemiplegia_side(subject: str) -> str:
    return "L" if subject in LEFT_HEMIPLEGIC else "R"


def mirror_permutation(channels: Sequence[str] = CHANNELS_40) -> np.ndarray:
    """Index array p such that X[..., p, :] swaps every left/right homologous pair.

    Applying it to a left-hemiplegic subject puts the hemisphere contralateral to the
    affected hand where it sits for right-hemiplegic subjects.
    """
    index = {name: i for i, name in enumerate(channels)}
    perm = np.arange(len(channels))
    for left, right in MIRROR_PAIRS:
        if left in index and right in index:
            perm[index[left]], perm[index[right]] = index[right], index[left]
    return perm


def mirror_if_needed(
    x: np.ndarray, subject: str, channels: Sequence[str] = CHANNELS_40
) -> np.ndarray:
    """Mirror channels for left-hemiplegic subjects; x has channels on axis -2."""
    if subject not in LEFT_HEMIPLEGIC:
        return x
    return x[..., mirror_permutation(channels), :]
