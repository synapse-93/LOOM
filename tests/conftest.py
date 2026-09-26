"""Shared pytest configuration, fixtures, and path setup."""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

# Ensure src/ and scripts/ are on sys.path for test discovery
ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

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


@pytest.fixture
def synthetic_video_path(tmp_path: Path) -> Path:
    """Generate a small 30-frame synthetic test video for fast unit/integration tests."""
    from generate_test_video import create_synthetic_test_video

    vid_path = tmp_path / "fixture_synthetic.mp4"
    return create_synthetic_test_video(
        output_path=vid_path,
        num_frames=30,
        fps=15,
        width=320,
        height=240,
    )
