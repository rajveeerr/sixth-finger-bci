import json
import subprocess

import numpy as np
import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from sixthfinger.cli import app
from sixthfinger.config import load_data_config
from sixthfinger.data.epochs import _settings
from sixthfinger.evaluation import runner as runner_mod
from sixthfinger.evaluation.runner import (
    UNIT_KEYS,
    map_ah_proxy,
    require_prereg,
    run_experiment,
    task_windows,
)
from sixthfinger.models.registry import REGISTRY, Batch, UndefinedCell, register
from sixthfinger.models.smoke import SmokeLogVarLda
from tests.evalfixtures import session_md

SUBJECTS = ("sub-01", "sub-03", "sub-07")


@pytest.fixture(scope="module")
def cache(tmp_path_factory):
    """A tiny epoch cache: 3 subjects, session pre, SF windows with more variance."""
    out = tmp_path_factory.mktemp("epochs")
    cfg = load_data_config()
    rng = np.random.default_rng(0)
    frames = []
    for subject in SUBJECTS:
        md = session_md(subject)
        name = f"{subject}_ses-pre.npz"
        X = rng.standard_normal((len(md), 40, 100)).astype(np.float32) * 1e-6
        X[md.label.to_numpy() == 2, 18:22] *= 1.6
        X[md.label.to_numpy() == 1, 10:14] *= 1.6
        np.savez(out / name, X=X)
        frames.append(
            md.assign(
                label_name=md.label.map({0: "rest", 1: "affected_hand", 2: "sixth_finger"}),
                group="B",
                hemiplegia_side="R",
                source_file=name,
                row_in_npz=np.arange(len(md)),
            )
        )
    pd.concat(frames, ignore_index=True).to_parquet(out / "metadata.parquet", index=False)
    (out / "manifest.json").write_text(json.dumps({**_settings(cfg), "files": {}}))
    return out


def _config(tmp_path, **fields):
    base = dict(
        name="smoke",
        protocol="within_session",
        within_protocols=["cv_leakfree", "chrono"],
        tasks=["T1_ah_vs_sf"],
        sessions=["pre"],
        subjects=["sub-01", "sub-03"],
        methods=["smoke_logvar_lda", "smoke_prior"],
    )
    path = tmp_path / f"{fields.get('name', 'smoke')}.yaml"
    path.write_text(yaml.safe_dump({**base, **fields}))
    return path


def _run(cfg_path, cache, tmp_path, **kw):
    return run_experiment(cfg_path, epochs_dir=cache, runs_dir=tmp_path / "runs", **kw)


def test_within_session_rows_resume_and_provenance(cache, tmp_path):
    cfg = _config(tmp_path)
    out = _run(cfg, cache, tmp_path)
    scores = pd.read_parquet(out)
    # 100 CV folds + 1 chrono split, for 2 subjects and 2 methods.
    assert len(scores) == 2 * 2 * 101
    assert set(scores.subject) == {"sub-01", "sub-03"}
    assert set(scores.protocol) == {"cv_leakfree", "chrono"}
    assert scores.bal_acc.between(0, 1).all()
    assert scores[scores.method == "smoke_prior"].bal_acc.eq(0.5).all()
    for col in ("git_sha", "config_hash", "data_manifest_sha", "created_at"):
        assert scores[col].notna().all() and (scores[col] != "").all()
    _run(cfg, cache, tmp_path)
    again = pd.read_parquet(out)
    assert len(again) == len(scores)
    assert not again.duplicated(UNIT_KEYS).any()


def test_paper_replica_and_loro_run(cache, tmp_path):
    cfg = _config(tmp_path, within_protocols=["paper_replica", "loro"], subjects=["sub-01"])
    scores = pd.read_parquet(_run(cfg, cache, tmp_path, methods=["smoke_logvar_lda"]))
    assert scores.groupby("protocol").size().to_dict() == {"loro": 4, "paper_replica": 100}


def test_crash_leaves_a_readable_file_and_resumes(cache, tmp_path, monkeypatch):
    calls = {"n": 0}

    @register("boom_after_30")
    class Boom(SmokeLogVarLda):
        def fit(self, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] > 30:
                raise RuntimeError("simulated crash")
            return super().fit(*args, **kwargs)

    try:
        cfg = _config(tmp_path, methods=["boom_after_30"], within_protocols=["cv_leakfree"])
        monkeypatch.setattr(runner_mod.ScoreWriter, "flush_every", 10)
        with pytest.raises(RuntimeError, match="simulated"):
            _run(cfg, cache, tmp_path)
        out = tmp_path / "runs" / "smoke" / "scores.parquet"
        assert len(pd.read_parquet(out)) == 30
        assert not out.with_suffix(".tmp").exists()
        calls["n"] = -1000
        _run(cfg, cache, tmp_path)
        scores = pd.read_parquet(out)
        assert len(scores) == 200 and not scores.duplicated(UNIT_KEYS).any()
    finally:
        REGISTRY.pop("boom_after_30")


def test_unknown_method_or_subject_is_an_error(cache, tmp_path):
    cfg = _config(tmp_path)
    with pytest.raises(ValueError, match="not in the experiment"):
        _run(cfg, cache, tmp_path, methods=["csp_ldaa"])
    with pytest.raises(ValueError, match="not in the experiment"):
        _run(cfg, cache, tmp_path, subjects=["sub-07"])


def _calib(tmp_path, **fields):
    base = dict(
        name="smoke_calib",
        protocol="calibration",
        within_protocols=[],
        tasks=["T2_rest_ah_sf", "T3_sf_vs_rest"],
        scenarios=["S1_new_user", "S2_new_command"],
        subjects=["sub-01"],
    )
    return _config(tmp_path, **{**base, **fields})


def test_calibration_quick_grid(cache, tmp_path):
    out = _run(_calib(tmp_path), cache, tmp_path, quick=True)
    assert out.parent.name == "smoke_calib_quick"
    scores = pd.read_parquet(out)
    assert set(scores.k) == {0, 2, 20}
    assert set(scores[scores.k == 2].draw) == {"0", "1", "chrono"}
    assert set(scores[scores.k.isin([0, 20])].draw) == {"0"}
    # From scratch has no SF example at k = 0 in either scenario: missing, never chance.
    k0 = scores[scores.k == 0]
    assert k0.bal_acc.isna().all() and (k0.reason == "no target data for every class").all()
    defined = scores[scores.k > 0]
    assert defined.bal_acc.between(0, 1).all()
    s2_t3 = defined[(defined.scenario == "S2_new_command") & (defined.task == "T3_sf_vs_rest")]
    assert s2_t3.sf_vs_ah.between(0, 1).all()
    assert defined[defined.scenario == "S1_new_user"].sf_vs_ah.isna().all()
    # k = 20 is capped at what the pool has; the fixture drops one SF trial in run 02.
    capped = scores[(scores.k == 20) & (scores.scenario == "S1_new_user")].k_used.iloc[0]
    assert json.loads(capped) == {"1": 20, "2": 19}
    t3 = defined[(defined.task == "T3_sf_vs_rest") & (defined.scenario == "S1_new_user")]
    assert (t3[t3.k == 2].n_train == 4).all()
    assert len(pd.read_parquet(_run(_calib(tmp_path), cache, tmp_path, quick=True))) == len(scores)


def test_ah_proxy_is_fitted_once_and_repeated_at_every_k(cache, tmp_path):
    fits = {"n": 0}
    real = REGISTRY["ah_proxy"]

    @register("ah_proxy")
    class Proxy(SmokeLogVarLda):
        def fit(self, target, *args, **kwargs):
            fits["n"] += 1
            assert set(target.y) == {0, 1}
            return super().fit(target, *args, **kwargs)

    try:
        cfg = _calib(tmp_path, scenarios=["S2_new_command"], methods=["ah_proxy"])
        scores = pd.read_parquet(_run(cfg, cache, tmp_path, quick=True))
    finally:
        REGISTRY["ah_proxy"] = real
    assert fits["n"] == 1
    assert set(scores.draw) == {"0"} and set(scores.k) == {0, 2, 20}
    assert scores.bal_acc.notna().all()
    for task, rows in scores.groupby("task"):
        assert (rows.bal_acc == rows.bal_acc.iloc[0]).all(), task
    assert scores[scores.task == "T3_sf_vs_rest"].sf_vs_ah.notna().all()


def test_task_windows_and_proxy_mapping():
    md = session_md(runs=(1,))
    t3 = task_windows(md, [0, 2])
    assert set(t3.label) == {0, 2} and (t3.groupby("trial_uid").label.max() == 2).all()
    assert len(task_windows(md, [0, 1, 2])) == len(md)
    proba = np.array([[0.7, 0.3], [0.2, 0.8]])
    assert np.allclose(map_ah_proxy(proba, [0, 2]), proba)
    assert np.allclose(map_ah_proxy(proba, [0, 1, 2]), [[0.7, 0.3, 0], [0.2, 0.8, 0]])


def test_cli_run_reports_rows(cache, tmp_path, monkeypatch):
    monkeypatch.setattr(
        runner_mod,
        "get_paths",
        lambda: type(
            "P",
            (),
            {
                "epochs": cache,
                "runs": tmp_path,
                "configs": tmp_path,
                "processed": tmp_path,
                "models": tmp_path,
            },
        )(),
    )
    cfg = _config(tmp_path, within_protocols=["chrono"])
    result = CliRunner().invoke(app, ["run", str(cfg), "--subjects", "sub-01"])
    assert result.exit_code == 0, result.output
    assert "2 rows" in result.output
    bad = CliRunner().invoke(app, ["run", str(cfg), "--methods", "nope"])
    assert bad.exit_code == 1


@pytest.fixture(scope="module")
def tree_and_cache(tmp_path_factory):
    """sub-05 (no follow-up session) from synthetic run files, and its epoch cache."""
    from sixthfinger.data import epochs
    from tests.conftest import synthetic_events, write_eeglab_mat

    root = tmp_path_factory.mktemp("processed")
    for session in ("pre", "post"):
        for run in ("01", "02", "03", "04"):
            name = f"sub-05_B_{session}_{run}_eeg.mat"
            seed = int(run) + (10 if session == "post" else 0)
            events = synthetic_events(n_trials=6, seed=seed)
            write_eeglab_mat(root / "sub-05" / session / name, events=events, seed=seed)
    out = tmp_path_factory.mktemp("epochs5")
    epochs.build_all(load_data_config(), root, out, subjects=["sub-05"])
    return root, out


def _rq1(tmp_path, **fields):
    base = dict(
        name="rq1_small",
        within_protocols=["paper_replica", "cv_leakfree", "loro", "chrono"],
        features=["bandpower", "ersp_mu"],
        subjects=["sub-05"],
        methods=["csp_lda_replica", "mdm"],
    )
    return _config(tmp_path, **{**base, **fields})


def test_replica_method_reads_the_ersp_input(tree_and_cache, tmp_path):
    root, cache = tree_and_cache
    out = run_experiment(
        _rq1(tmp_path), epochs_dir=cache, runs_dir=tmp_path / "runs", processed_dir=root
    )
    scores = pd.read_parquet(out)
    assert scores.groupby("method").feature.unique().map(list).to_dict() == {
        "csp_lda_replica": ["ersp_mu"],
        "mdm": ["bandpower"],
    }
    # 12 trials per class in a session: 10 folds x 10 repeats, 4 runs, one chrono split.
    counts = scores.groupby(["method", "protocol"]).size()
    expected = {"cv_leakfree": 100, "paper_replica": 100, "loro": 4, "chrono": 1}
    assert all(counts[(m, p)] == n for m in ("mdm", "csp_lda_replica") for p, n in expected.items())
    assert scores.bal_acc.between(0, 1).all()
    # MDM has nothing to fit before its classifier, so the replica cannot leak.
    mdm = scores[scores.method == "mdm"].set_index(["protocol", "fold"]).bal_acc
    assert np.array_equal(mdm["paper_replica"].to_numpy(), mdm["cv_leakfree"].to_numpy())
    resumed = run_experiment(
        _rq1(tmp_path), epochs_dir=cache, runs_dir=tmp_path / "runs", processed_dir=root
    )
    assert len(pd.read_parquet(resumed)) == len(scores)


def test_parallel_jobs_give_the_same_rows(tree_and_cache, tmp_path):
    root, cache = tree_and_cache
    cfg = _rq1(
        tmp_path,
        sessions=["pre", "post"],
        within_protocols=["paper_replica", "loro", "chrono"],
        methods=["csp_lda", "csp_lda_replica"],
    )
    frames = []
    for n_jobs in (1, 2):
        out = run_experiment(
            cfg,
            n_jobs=n_jobs,
            epochs_dir=cache,
            runs_dir=tmp_path / f"runs{n_jobs}",
            processed_dir=root,
        )
        scores = pd.read_parquet(out).sort_values(UNIT_KEYS, ignore_index=True)
        frames.append(scores)
    cols = ["bal_acc", "acc", "kappa", "confusion", "n_train", "n_test", "n_folds"]
    assert len(frames[0]) == len(frames[1]) > 0
    pd.testing.assert_frame_equal(frames[0][UNIT_KEYS + cols], frames[1][UNIT_KEYS + cols])


def test_calibration_refuses_a_method_with_another_input(cache, tmp_path):
    cfg = _calib(tmp_path, methods=["csp_lda_replica"])
    with pytest.raises(ValueError, match="cached windows"):
        _run(cfg, cache, tmp_path, quick=True)


def test_ersp_input_refuses_rest_windows(tree_and_cache):
    from sixthfinger.evaluation.runner import ersp_input

    root, cache = tree_and_cache
    md = pd.read_parquet(cache / "metadata.parquet")
    settings = {"band_hz": [8.0, 13.0], "baseline_s": [-1.0, 0.0]}
    with pytest.raises(ValueError, match="REST"):
        ersp_input(md, load_data_config(), root, settings)
    mi = md[(md.label > 0) & (md.session == "pre")]
    rows, X = ersp_input(mi, load_data_config(), root, settings)
    assert len(rows) == len(mi) and X.shape == (len(mi), 40, 1000)
    assert rows.index.tolist() == list(range(len(rows)))


def test_within_session_seeds_are_separate_units(cache, tmp_path):
    cfg = _config(tmp_path, name="seeded", within_protocols=["chrono"], seeds=[0, 1, 2])
    scores = pd.read_parquet(_run(cfg, cache, tmp_path, methods=["smoke_logvar_lda"]))
    assert sorted(scores.draw.unique()) == ["0", "1", "2"]
    assert len(scores) == 2 * 3  # two subjects, one chrono split, three seeds
    again = pd.read_parquet(_run(cfg, cache, tmp_path, methods=["smoke_logvar_lda"]))
    assert len(again) == len(scores) and not again.duplicated(UNIT_KEYS).any()


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_full_cohort_calibration_needs_the_prereg_tag(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(
        tmp_path,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "c",
    )
    dev = ["sub-01", "sub-03"]
    require_prereg(["sub-01"], dev, tmp_path)  # development subjects only: always allowed
    with pytest.raises(RuntimeError, match="prereg-v1"):
        require_prereg(["sub-01", "sub-05"], dev, tmp_path)
    _git(tmp_path, "tag", "prereg-v1")
    require_prereg(["sub-01", "sub-05"], dev, tmp_path)


def test_a_bundle_without_git_needs_the_stamp(tmp_path):
    with pytest.raises(RuntimeError, match="prereg-v1"):
        require_prereg(["sub-05"], ["sub-01"], tmp_path)
    (tmp_path / "PREREG").write_text("prereg-v1 caea954\n")
    require_prereg(["sub-05"], ["sub-01"], tmp_path)


def _spy(name, seen):
    @register(name)
    class Spy(SmokeLogVarLda):
        def fit(self, target, source=None, unlabelled=None, seed=0):
            seen.append((target, unlabelled))
            return super().fit(target, source, unlabelled, seed)

    return Spy


def test_parallel_calibration_gives_the_same_rows(cache, tmp_path):
    kw = dict(subjects=["sub-01", "sub-03"], tasks=["T2_rest_ah_sf"])
    one = pd.read_parquet(_run(_calib(tmp_path, name="c_one", **kw), cache, tmp_path, quick=True))
    out = _run(_calib(tmp_path, name="c_two", **kw), cache, tmp_path, quick=True, n_jobs=2)
    two = pd.read_parquet(out)
    assert not list((out.parent / "parts").glob("*.parquet"))
    keys = [k for k in UNIT_KEYS if k != "experiment"]
    a, b = (f.sort_values(keys).reset_index(drop=True) for f in (one, two))
    pd.testing.assert_frame_equal(a[[*keys, "bal_acc"]], b[[*keys, "bal_acc"]])


def test_a_one_job_resume_folds_in_the_parts_of_a_stopped_parallel_run(cache, tmp_path):
    kw = dict(subjects=["sub-01", "sub-03"], tasks=["T3_sf_vs_rest"])
    out = _run(_calib(tmp_path, name="c_parts", **kw), cache, tmp_path, quick=True)
    full = pd.read_parquet(out)
    # As if the run had stopped after sub-03's worker wrote its part file.
    (out.parent / "parts").mkdir()
    full[full.subject == "sub-03"].to_parquet(out.parent / "parts" / "sub-03.parquet")
    full[full.subject == "sub-01"].to_parquet(out)
    resumed = pd.read_parquet(_run(_calib(tmp_path, name="c_parts", **kw), cache, tmp_path,
                                   quick=True))  # fmt: skip
    assert len(resumed) == len(full) and set(resumed.subject) == {"sub-01", "sub-03"}
    assert not list((out.parent / "parts").glob("*.parquet"))


def test_the_unlabelled_set_is_the_rest_set_at_k0_and_the_drawn_windows_after(cache, tmp_path):
    seen = []

    @register("spy_unlabelled")
    class Spy(SmokeLogVarLda):
        uses_source = True  # a transfer method is fitted at k = 0 too

        def fit(self, target, source=None, unlabelled=None, seed=0):
            seen.append((target, unlabelled))
            if not len(target.md):
                raise UndefinedCell("recorded only")
            return super().fit(target, source, unlabelled, seed)

    try:
        cfg = _calib(tmp_path, methods=["spy_unlabelled"], scenarios=["S1_new_user"])
        _run(cfg, cache, tmp_path, quick=True)
    finally:
        REGISTRY.pop("spy_unlabelled")
    k0 = [(t, u) for t, u in seen if len(t.md) == 0]
    later = [(t, u) for t, u in seen if len(t.md) > 0]
    assert k0 and later
    for _, unl in k0:  # every REST window of the pool, nothing else
        assert set(unl.md.run) <= {1, 2} and len(unl.md) == 40
    for target, unl in later:  # T3 included: not the AH trials the draw also holds
        assert list(unl.md.index) == list(target.md.index)


def test_a_resume_refuses_rows_made_with_other_settings(cache, tmp_path):
    _run(_calib(tmp_path, tasks=["T3_sf_vs_rest"]), cache, tmp_path, quick=True)
    changed = _calib(tmp_path, tasks=["T3_sf_vs_rest"], params={"smoke_prior": {"x": 1}})
    with pytest.raises(ValueError, match="other settings"):
        _run(changed, cache, tmp_path, quick=True)


def test_pool_and_test_runs_can_be_overridden(cache, tmp_path):
    seen = []
    _spy("spy_runs", seen)
    try:
        cfg = _calib(
            tmp_path, methods=["spy_runs"], tasks=["T2_rest_ah_sf"], scenarios=["S1_new_user"],
            pool_runs=["01"], test_runs=["02"],
        )  # fmt: skip
        scores = pd.read_parquet(_run(cfg, cache, tmp_path, quick=True))
    finally:
        REGISTRY.pop("spy_runs")
    assert {r for target, _ in seen for r in target.md.run} == {1}
    # Run 02 of the fixture has 20 REST and 19 imagery windows (one dropped).
    assert set(scores.dropna(subset=["bal_acc"]).n_test) == {39}


def test_unlabelled_windows_reach_a_method_without_labels(cache, tmp_path):
    seen = []
    _spy("spy_labels", seen)
    try:
        cfg = _calib(tmp_path, methods=["spy_labels"], tasks=["T3_sf_vs_rest"])
        _run(cfg, cache, tmp_path, quick=True)
    finally:
        REGISTRY.pop("spy_labels")
    assert seen
    for _, unlabelled in seen:
        assert unlabelled.y is None and "label" not in unlabelled.md.columns


def test_an_undefined_cell_is_written_as_missing_in_calibration(cache, tmp_path):
    @register("undefined_here")
    class Undefined(SmokeLogVarLda):
        def fit(self, *args, **kwargs):
            raise UndefinedCell("no solution on this training set")

    try:
        cfg = _calib(tmp_path, methods=["undefined_here"], tasks=["T3_sf_vs_rest"])
        scores = pd.read_parquet(_run(cfg, cache, tmp_path, quick=True))
    finally:
        REGISTRY.pop("undefined_here")
    defined_k = scores[scores.k > 0]
    assert defined_k.bal_acc.isna().all()
    assert set(defined_k.reason) == {"no solution on this training set"}


def test_the_chronological_draw_goes_to_the_listed_methods_only(cache, tmp_path):
    cfg = _calib(tmp_path, tasks=["T3_sf_vs_rest"], chrono_methods=["smoke_prior"])
    scores = pd.read_parquet(_run(cfg, cache, tmp_path, quick=True))
    chrono = scores[scores.draw == "chrono"]
    assert set(chrono.method) == {"smoke_prior"}


def test_permuted_labels_keep_each_subjects_classes():
    md = pd.DataFrame({"subject": ["a"] * 6 + ["b"] * 4, "label": [0, 0, 0, 2, 2, 2, 0, 1, 1, 1]})
    batch = Batch(None, md.label.to_numpy(), md)
    out = runner_mod.permuted(batch, seed=0)
    for s in ("a", "b"):
        rows = (md.subject == s).to_numpy()
        assert sorted(out.y[rows]) == sorted(batch.y[rows])
    assert not np.array_equal(out.y, batch.y)
    np.testing.assert_array_equal(batch.y, md.label)  # the input is not changed


def test_rct_tslr_runs_end_to_end_with_the_covariance_store(cache, tmp_path):
    cfg = _calib(
        tmp_path, methods=["rct_tslr", "pooled_tslr"], params={"rct_tslr": {"target_weight": 5}},
    )  # fmt: skip
    scores = pd.read_parquet(_run(cfg, cache, tmp_path, quick=True))
    # Transfer is defined at every k, k = 0 included, in both scenarios and tasks.
    assert scores.bal_acc.notna().all(), scores[scores.bal_acc.isna()].reason.unique()
    assert set(scores.k) == {0, 2, 20}
