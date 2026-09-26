"""Shared pytest configuration, fixtures, and path setup."""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

# Ensure src/ is on sys.path for test discovery
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from loom.config.models import LoomConfig


@pytest.fixture
def sample_config() -> LoomConfig:
    """Provide a default LoomConfig instance for testing."""
    return LoomConfig()


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    """Provide an isolated temporary workspace directory."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace
