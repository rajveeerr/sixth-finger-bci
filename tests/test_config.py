import pydantic
import pytest
import yaml

from sixthfinger.config import (
    ProtocolConfig,
    config_hash,
    load_data_config,
    load_protocol_config,
)
from sixthfinger.paths import get_paths


def test_configs_load():
    data = load_data_config()
    protocol = load_protocol_config()
    assert data.n_times == 1000
    assert [lab.name for lab in data.labels] == ["rest", "affected_hand", "sixth_finger"]
    assert protocol.calibration.k_grid[0] == 0


def test_exclusions_and_links():
    cfg = load_data_config()
    assert cfg.sessions_for("sub-02") == ["pre", "post"]
    assert cfg.sessions_for("sub-05") == ["pre", "post"]
    assert cfg.sessions_for("sub-01") == ["pre", "post", "follow"]
    assert cfg.split_group("sub-21") == cfg.split_group("sub-22")
    assert cfg.split_group("sub-01") == "sub-01"
    assert cfg.is_run_excluded("sub-15", "follow", "02")
    assert not cfg.is_run_excluded("sub-15", "follow", "01")
    assert cfg.is_run_excluded("sub-02", "follow", "01")


def test_label_codes():
    cfg = load_data_config()
    assert cfg.label_by_code["3"].name == "sixth_finger"
    assert cfg.label_by_name["rest"].command == "IDLE"


def test_overlapping_calibration_runs_rejected():
    raw = yaml.safe_load((get_paths().configs / "protocol.yaml").read_text())
    raw["calibration"]["test_runs"] = ["02", "03"]
    with pytest.raises(pydantic.ValidationError):
        ProtocolConfig.model_validate(raw)


def test_unknown_key_rejected():
    raw = yaml.safe_load((get_paths().configs / "protocol.yaml").read_text())
    raw["calibration"]["k_gird"] = [1]
    with pytest.raises(pydantic.ValidationError):
        ProtocolConfig.model_validate(raw)


def test_config_hash_is_stable():
    a = config_hash(load_data_config(), load_protocol_config())
    b = config_hash(load_data_config(), load_protocol_config())
    assert a == b and len(a) == 16


def test_git_sha_comes_from_the_environment_when_set(monkeypatch):
    from sixthfinger.paths import current_git_sha

    monkeypatch.setenv("SIXTHFINGER_GIT_SHA", "abc1234")
    assert current_git_sha() == "abc1234"


def test_git_sha_is_marked_dirty_when_code_differs(monkeypatch, tmp_path):
    import subprocess

    from sixthfinger.paths import current_git_sha

    monkeypatch.delenv("SIXTHFINGER_GIT_SHA", raising=False)
    monkeypatch.setenv("SIXTHFINGER_ROOT", str(tmp_path))

    def run(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    run("init", "-q")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    (tmp_path / "notes.md").write_text("n\n")
    run("add", ".")
    run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "c")
    clean = current_git_sha()
    assert clean and not clean.endswith("-dirty")
    (tmp_path / "notes.md").write_text("changed\n")
    assert current_git_sha() == clean  # notes are not code
    (tmp_path / "src" / "a.py").write_text("x = 2\n")
    assert current_git_sha() == clean + "-dirty"
    run("checkout", "--", "src/a.py")
    (tmp_path / "src" / "new.py").write_text("y = 1\n")  # untracked code counts too
    assert current_git_sha() == clean + "-dirty"
