"""Canonical locations of data, configs and results."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def find_root() -> Path:
    """Repository root, overridable with SIXTHFINGER_ROOT (useful on Kaggle/Colab)."""
    env = os.environ.get("SIXTHFINGER_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file() and (parent / "configs").is_dir():
            return parent
    return Path.cwd()


@dataclass(frozen=True)
class Paths:
    root: Path
    data: Path

    @property
    def configs(self) -> Path:
        return self.root / "configs"

    @property
    def raw(self) -> Path:
        return self.data / "raw"

    @property
    def figshare(self) -> Path:
        return self.raw / "figshare"

    @property
    def metadata(self) -> Path:
        return self.figshare / "meta"

    @property
    def processed(self) -> Path:
        return self.data / "processed"

    @property
    def source(self) -> Path:
        return self.data / "source"

    @property
    def derived(self) -> Path:
        return self.data / "derived"

    @property
    def epochs(self) -> Path:
        return self.derived / "epochs"

    @property
    def results(self) -> Path:
        return self.root / "results"

    @property
    def audit(self) -> Path:
        return self.results / "audit"

    @property
    def summary(self) -> Path:
        return self.results / "summary"

    @property
    def runs(self) -> Path:
        return self.results / "runs"

    @property
    def figures(self) -> Path:
        return self.root / "docs" / "figures"

    @property
    def models(self) -> Path:
        return self.root / "models"


def get_paths() -> Paths:
    """Resolve paths; SIXTHFINGER_DATA moves only the (large) data directory."""
    root = find_root()
    data = Path(os.environ.get("SIXTHFINGER_DATA", root / "data")).expanduser().resolve()
    return Paths(root=root, data=data)


def current_git_sha() -> str:
    import subprocess

    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=find_root(),
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"
