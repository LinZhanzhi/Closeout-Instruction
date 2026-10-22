from pathlib import Path

import pytest

from src.config import load_config

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def config() -> dict:
    # Loaded through the same checks the program runs at startup, so a config.yaml that the
    # program would refuse fails the whole test run before anything is built or shipped.
    return load_config(PROJECT_ROOT / "config.yaml")
