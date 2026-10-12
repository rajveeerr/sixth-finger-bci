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
    x[5, (2 * 128) : (3 * 128)] += 400  # inside the first 5 s, which are dropped
    x[3, (10 * 128) : (11 * 128)] += 400  # one artefact inside segment 2 (5 s skipped)
    segs = rq5.segment(x, 128)
    assert segs.shape[1:] == (19, 512)
    assert len(segs) == 75 - 1  # 300 s of 320 kept; without the skip it would be 75 - 2
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


def test_shuffled_diagnoses_keep_group_sizes_and_split_groups(rq5):
    _, md = _identity_only(n_per_group=6, n_seg=3)
    md.loc[md.subject.isin(["H-S1", "H-S2"]), "split_group"] = "H-S1+H-S2"
    for seed in range(5):
        s = rq5.shuffled(md, seed)
        per_group = s.drop_duplicates("split_group").group.value_counts()
        assert (
            per_group.to_dict() == md.drop_duplicates("split_group").group.value_counts().to_dict()
        )
        assert s.groupby("split_group").group.nunique().eq(1).all()  # a group shares one label
    assert any(not rq5.shuffled(md, seed).group.equals(md.group) for seed in range(5))


def test_inflation_ci_resamples_within_each_group(rq5):
    # Three H subjects inflate by 1.0, 47 MDD subjects by 0. Resampling within groups keeps
    # three H subjects in every resample, so every resample gives (1 + 0) / 2 exactly; pooled
    # resampling would sometimes draw no H subject, and a plain mean would give 0.06.
    groups = np.array(["H"] * 3 + ["MDD"] * 47)
    a_seg = np.where(groups == "H", 1.0, 0.5)
    a_sub = np.where(groups == "H", 0.0, 0.5)
    assert rq5.stratified_inflation_ci(a_seg, a_sub, groups, n=2000) == (0.5, 0.5, 0.5)


def test_inflation_ci_is_stratified_and_contains_the_point(rq5):
    rng = np.random.default_rng(0)
    groups = np.array(["H"] * 20 + ["MDD"] * 30)
    a_sub = rng.uniform(0.4, 0.7, 50)
    a_seg = np.clip(a_sub + 0.2, 0, 1)
    point, lo, hi = rq5.stratified_inflation_ci(a_seg, a_sub, groups, n=2000)
    expected = np.mean([a_seg[groups == g].mean() for g in ("H", "MDD")]) - np.mean(
        [a_sub[groups == g].mean() for g in ("H", "MDD")]
    )
    assert point == pytest.approx(expected)
    assert lo <= point <= hi


def test_preprocessing_returns_microvolts(rq5):
    import mne

    t = np.arange(60 * 256) / 256
    x = np.zeros((19, t.size))
    x[0] = 50e-6 * np.sin(2 * np.pi * 10 * t)  # 50 µV at 10 Hz, in volts as MNE holds it
    raw = mne.io.RawArray(x, mne.create_info(rq5.CHANNELS, 256, "eeg"), verbose="ERROR")
    out = rq5.preprocess(raw, {c: c for c in rq5.CHANNELS})
    peak = np.abs(out[0, 128 * 5 : -128 * 5]).max()
    assert peak == pytest.approx(50 * 18 / 19, rel=0.02)  # less its share of the average


def test_modma_channels_pick_the_preregistered_rows_in_volts(rq5):
    data = np.arange(129, dtype=float)[:, None] * np.ones((1, 4))  # row i holds i µV
    x = rq5.modma_channels(data)
    assert x.shape == (19, 4)
    assert x[rq5.CHANNELS.index("Fp1"), 0] == pytest.approx(21e-6)  # E22 is row 21
    assert x[rq5.CHANNELS.index("Cz"), 0] == pytest.approx(128e-6)  # the reference row


@pytest.mark.parametrize(("freq", "band"), [(2, 0), (6, 1), (10, 2), (20, 3), (35, 4)])
def test_band_power_puts_a_sine_in_its_band(rq5, freq, band):
    t = np.arange(512) / 128
    x = np.random.default_rng(0).normal(0, 0.01, (1, 19, 512))
    x[0, 4] += np.sin(2 * np.pi * freq * t)
    feats = rq5.LogBandPower().transform(x).reshape(19, 5)
    assert feats[4].argmax() == band


def test_holm_across_pipelines_sets_the_category(rq5):
    stats = pd.DataFrame(dict(dataset=["a", "a", "b", "b", "c", "c"],
                              pipeline=["bp_lr", "ts_lr"] * 3,
                              p=[0.01, 0.02, 0.01, 0.06, 0.03, 0.2]))  # fmt: skip
    out = rq5.categorise(stats).set_index(["dataset", "pipeline"])
    assert out.loc[("a", "bp_lr"), "p_holm"] == pytest.approx(0.02)
    assert out.loc[("b", "ts_lr"), "p_holm"] == pytest.approx(0.06)
    assert set(out.loc["a"].category) == {"supported"}
    assert set(out.loc["b"].category) == {"partial"}  # only 0.01 survives (adjusted 0.02)
    assert set(out.loc["c"].category) == {"inconclusive"}  # 0.03 adjusts to 0.06


def _people(spec):
    rows = []
    for year, group, n, gad7 in spec:
        rows += [dict(subject=f"{group}-{len(rows) + i}", group=group, year=year, gad7=gad7)
                 for i in range(n)]  # fmt: skip
    return pd.DataFrame(rows)


def test_e1_uses_only_years_with_ten_per_group(rq5):
    md = _people([(2011, "H", 9, 0), (2013, "H", 18, 0), (2013, "MDD", 29, 0)])
    assert rq5.e1_years(md) == [2013]
    assert rq5.e1_years(_people([(2013, "H", 9, 0), (2013, "MDD", 29, 0)])) == []


def test_e3_relabels_by_gad7_only_when_both_sides_reach_ten(rq5):
    md = _people([(0, "H", 29, 3), (0, "MDD", 4, 5), (0, "MDD", 19, 12)])
    ma = rq5.gad7_groups(md)
    assert ma.drop_duplicates("subject").group.value_counts().to_dict() == {"H": 33, "MDD": 19}
    assert rq5.gad7_groups(_people([(0, "H", 29, 3), (0, "MDD", 9, 12)])) is None
