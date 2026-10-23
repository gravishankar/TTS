from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def config_dir() -> Path:
    return REPO_ROOT / "configs"
