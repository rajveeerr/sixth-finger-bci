import os
from dataclasses import dataclass, field
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = SERVER_DIR.parent


def _default_bundle_dir() -> Path:
    # Inside the container the bundle is copied next to the app; in the repo the
    # web app's public bundle is the single source of truth.
    for candidate in (SERVER_DIR / "bundle", REPO_DIR / "web" / "public" / "demo"):
        if (candidate / "manifest.json").exists():
            return candidate
    return SERVER_DIR / "bundle"


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    bundle_dir: Path = field(default_factory=_default_bundle_dir)
    allowed_origins: list[str] = field(default_factory=lambda: ["*"])
    max_speed: float = 8.0
    max_streams: int = 8
    chunk_samples: int = 20
    hop_seconds: float = 0.5

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        return cls(
            bundle_dir=Path(os.environ.get("BUNDLE_DIR", defaults.bundle_dir)),
            allowed_origins=_csv(os.environ.get("ALLOWED_ORIGINS", "*")),
            max_speed=float(os.environ.get("MAX_SPEED", defaults.max_speed)),
            max_streams=int(os.environ.get("MAX_STREAMS", defaults.max_streams)),
        )
