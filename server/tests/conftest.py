from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.bundle import Bundle
from app.main import create_app
from app.settings import Settings
from app.synthetic import build_bundle

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def bundle_dir(tmp_path_factory) -> Path:
    return build_bundle(tmp_path_factory.mktemp("bundle"), FIXTURES / "test_model.onnx", n_trials=4)


@pytest.fixture(scope="session")
def bundle(bundle_dir) -> Bundle:
    return Bundle(bundle_dir)


@pytest.fixture()
def client(bundle_dir):
    settings = Settings(bundle_dir=bundle_dir, max_speed=10_000.0, max_streams=2)
    with TestClient(create_app(settings)) as test_client:
        yield test_client
