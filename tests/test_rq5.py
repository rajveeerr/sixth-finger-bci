import importlib.util

import numpy as np
import pandas as pd
import pytest

from sixthfinger.paths import get_paths


@pytest.fixture(scope="module")
def rq5():
    path = get_paths().root / "scripts" / "rq5_depression.py"
    spec = importlib.util.spec_from_file_location("rq5_depression", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _edf_header(tmp_path, name, patient, date="15.03.13"):
    head = bytearray(b" " * 256)
    head[0:8] = b"0       "
    head[8 : 8 + len(patient)] = patient.encode()
    head[168:176] = date.encode()
    path = tmp_path / name
    path.write_bytes(bytes(head))
    return path


def test_header_fields_are_hashed_never_returned(rq5, tmp_path):
    a = _edf_header(tmp_path, "a.edf", "X Jane Fakename 01-JAN-1970")
    b = _edf_header(tmp_path, "b.edf", "X Jane Fakename 01-JAN-1970")
    c = _edf_header(tmp_path, "c.edf", "X Other Person 02-FEB-1971", date="01.06.11")
    ha, hb, hc = (rq5.edf_patient_hash(p) for p in (a, b, c))
    assert ha == hb != hc
    assert "Fakename" not in ha and len(ha) == 64
    assert rq5.edf_start_year(a) == 2013 and rq5.edf_start_year(c) == 2011


def test_channel_labels_match_the_preregistered_rule(rq5):
    labels = ["EEG Fp1-LE", "EEG FP2-LE", *[f"EEG {c}-LE" for c in rq5.CHANNELS[2:]], "EEG A2-A1"]
    picks = rq5.match_channels(labels, rq5.CHANNELS)
    assert picks["Fp2"] == "EEG FP2-LE" and len(picks) == 19
    assert rq5.match_channels(labels[1:], rq5.CHANNELS) is None  # Fp1 missing


def test_segments_drop_the_start_keep_300_s_and_reject_artefacts(rq5):
    rng = np.random.default_rng(0)
    x = rng.normal(0, 10, (19, (320 * 128)))
    x[3, (10 * 128) : (11 * 128)] += 400  # one artefact inside segment 2 (5 s skipped)
    segs = rq5.segment(x, 128)
    assert segs.shape[1:] == (19, 512)
    assert len(segs) == 75 - 1
    flat = x.copy()
    flat[0] = 0.0
    assert len(rq5.segment(flat, 128)) == 0


def _identity_only(n_per_group=12, n_seg=30, seed=0):
    """Each subject has its own spatial signature; the groups do not differ at all."""
    rng = np.random.default_rng(seed)
    Xs, rows = [], []
    for g in ("H", "MDD"):
        for i in range(n_per_group):
            mix = np.eye(19) + 0.8 * rng.standard_normal((19, 19))
            Xs.append(np.einsum("cd,ndt->nct", mix, rng.standard_normal((n_seg, 19, 512))))
            s = f"{g}-S{i + 1}"
            rows += [dict(subject=s, group=g, split_group=s, segment=j) for j in range(n_seg)]
    return np.concatenate(Xs).astype(np.float32), pd.DataFrame(rows)


def test_subject_cv_keeps_subjects_whole_and_segment_cv_does_not(rq5):
    _, md = _identity_only()
    md.loc[md.subject == "H-S2", "split_group"] = "H-S1+H-S2"
    md.loc[md.subject == "H-S1", "split_group"] = "H-S1+H-S2"
    for train, test in rq5.splits(md, "subject_cv"):
        assert not set(md.split_group.iloc[train]) & set(md.split_group.iloc[test])
    mixed = sum(bool(set(md.subject.iloc[tr]) & set(md.subject.iloc[te]))
                for tr, te in rq5.splits(md, "segment_cv"))  # fmt: skip
    assert mixed == 10
    for protocol in rq5.PROTOCOLS:
        tested = np.concatenate([te for _, te in rq5.splits(md, protocol)])
        assert sorted(tested) == list(range(len(md)))  # every segment once


def test_person_identity_alone_inflates_segment_cv_only(rq5):
    X, md = _identity_only()
    ba = {}
    for protocol in rq5.PROTOCOLS:
        values = rq5.per_subject(rq5.evaluate(X, md, "ts_lr", protocol))
        ba[protocol] = rq5.subject_balanced_accuracy(values)
    assert ba["segment_cv"] > 0.9
    # No inflation under subject_cv. On null data it can even fall below 0.5: holding out a
    # group's subjects tilts the training set towards the other group.
    assert ba["subject_cv"] < 0.65
