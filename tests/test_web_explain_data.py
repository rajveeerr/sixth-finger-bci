"""The demo page's explanatory figures carry the current results (P11 polish)."""

import importlib.util
import json

import pytest

from sixthfinger.paths import get_paths


@pytest.fixture(scope="module")
def module():
    path = get_paths().root / "scripts" / "make_web_explain_data.py"
    spec = importlib.util.spec_from_file_location("make_web_explain_data", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_page_numbers_match_the_results(module):
    committed = json.loads(get_paths().root.joinpath(*module.OUT).read_text())
    assert module.build() == committed, "run: uv run python scripts/make_web_explain_data.py"


def test_page_numbers_are_sane(module):
    data = module.build()
    assert len(data["electrodes"]) == 40
    assert sum(e["shown"] for e in data["electrodes"]) == 7
    assert all(abs(e["x"]) <= 1.2 and abs(e["y"]) <= 1.2 for e in data["electrodes"])
    for task in data["tasks"]:
        assert len(task["values"]) == 22
        assert task["chance"] < task["mean"] < 1
    leak = data["leak"]
    assert len(leak["replica"]) == len(leak["leakfree"]) == len(leak["subjects"])
    assert leak["mean_replica"] > leak["mean_leakfree"]
    for curve in data["calibration"].values():
        assert [p["k"] for p in curve] == sorted(p["k"] for p in curve)
        assert all(p["ci"][0] <= p["mean"] <= p["ci"][1] for p in curve)
