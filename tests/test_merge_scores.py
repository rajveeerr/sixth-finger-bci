import importlib.util

import pandas as pd
import pytest

from sixthfinger.paths import get_paths


@pytest.fixture(scope="module")
def merge():
    path = get_paths().root / "scripts" / "merge_scores.py"
    spec = importlib.util.spec_from_file_location("merge_scores", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rows(hash_a="h1"):
    return pd.DataFrame(
        {"method": ["a", "a", "b"], "subject": ["sub-01", "sub-03", "sub-01"],
         "config_hash": [hash_a, hash_a, "h2"]}
    )  # fmt: skip


def test_rows_with_their_expected_hash_are_accepted(merge, tmp_path, monkeypatch):
    monkeypatch.setattr(merge, "expected_hashes", lambda e, rows: {"a": "h1", "b": "h2"})
    _rows().to_parquet(tmp_path / "s.parquet")
    assert len(merge.check("x", tmp_path / "s.parquet")) == 3


def test_rows_made_with_other_settings_are_refused(merge, tmp_path, monkeypatch):
    monkeypatch.setattr(merge, "expected_hashes", lambda e, rows: {"a": "h1", "b": "h2"})
    _rows(hash_a="other").to_parquet(tmp_path / "s.parquet")
    with pytest.raises(SystemExit, match="other settings"):
        merge.check("x", tmp_path / "s.parquet")


def test_the_expected_hash_depends_on_the_subjects_of_the_file(merge):
    rows = pd.DataFrame({"method": ["ts_lr"], "subject": ["sub-01"]})
    one = merge.expected_hashes("rq2_rq3_post", rows)
    two = merge.expected_hashes("rq2_rq3_post", pd.concat([rows, rows.assign(subject="sub-05")]))
    assert one["ts_lr"] != two["ts_lr"]


def _unit_rows(created_at, bal_acc):
    keys = dict(experiment="x", protocol="calib", scenario="S1_new_user", task="T2_rest_ah_sf",
                method="a", feature="bandpower", subject="sub-01", session="pre", k=1, draw="0",
                fold=0)  # fmt: skip
    return pd.DataFrame([{**keys, "created_at": created_at, "bal_acc": bal_acc}])


def test_a_unit_keeps_its_newest_row(merge, tmp_path, monkeypatch):
    monkeypatch.setattr(merge, "check", lambda e, f: pd.read_parquet(f))
    out = tmp_path / "runs" / "x" / "scores.parquet"
    out.parent.mkdir(parents=True)
    _unit_rows("2026-10-12T10:00:00", 0.5).to_parquet(out)
    _unit_rows("2026-10-12T11:00:00", 0.6).to_parquet(tmp_path / "new.parquet")
    merged = merge.merge("x", [tmp_path / "new.parquet"], out)
    assert merged.bal_acc.tolist() == [0.6]


def test_merging_refuses_while_a_stopped_run_has_parts(merge, tmp_path):
    out = tmp_path / "runs" / "x" / "scores.parquet"
    (out.parent / "parts").mkdir(parents=True)
    _unit_rows("2026-10-12T10:00:00", 0.5).to_parquet(out.parent / "parts" / "sub-01.parquet")
    with pytest.raises(SystemExit, match="stopped run"):
        merge.merge("x", [], out)


def test_the_newest_row_wins_whatever_the_order_of_the_frames(merge, tmp_path, monkeypatch):
    monkeypatch.setattr(merge, "check", lambda e, f: pd.read_parquet(f))
    out = tmp_path / "runs" / "x" / "scores.parquet"
    out.parent.mkdir(parents=True)
    _unit_rows("2026-10-12T11:00:00", 0.6).to_parquet(out)  # the newer row, read first
    _unit_rows("2026-10-12T10:00:00", 0.5).to_parquet(tmp_path / "old.parquet")
    assert merge.merge("x", [tmp_path / "old.parquet"], out).bal_acc.tolist() == [0.6]
