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


@pytest.fixture
def clean_cube_obj(tmp_path: Path) -> Path:
    """Fixture providing a clean watertight cube OBJ file."""
    from tests.fixtures.mesh_fixtures import create_clean_cube, save_fixture_mesh
    mesh = create_clean_cube()
    return save_fixture_mesh(mesh, tmp_path / "clean_cube.obj", "obj")


@pytest.fixture
def disconnected_mesh_obj(tmp_path: Path) -> Path:
    """Fixture providing a disconnected 2-component OBJ file."""
    from tests.fixtures.mesh_fixtures import create_disconnected_mesh, save_fixture_mesh
    mesh = create_disconnected_mesh()
    return save_fixture_mesh(mesh, tmp_path / "disconnected.obj", "obj")


@pytest.fixture
def degenerate_mesh_obj(tmp_path: Path) -> Path:
    """Fixture providing a mesh with zero-area degenerate faces."""
    from tests.fixtures.mesh_fixtures import create_degenerate_mesh, save_fixture_mesh
    mesh = create_degenerate_mesh()
    return save_fixture_mesh(mesh, tmp_path / "degenerate.obj", "obj")


@pytest.fixture
def hole_mesh_obj(tmp_path: Path) -> Path:
    """Fixture providing a mesh with a small boundary hole."""
    from tests.fixtures.mesh_fixtures import create_hole_mesh, save_fixture_mesh
    mesh = create_hole_mesh()
    return save_fixture_mesh(mesh, tmp_path / "hole.obj", "obj")


@pytest.fixture
def large_hole_mesh_obj(tmp_path: Path) -> Path:
    """Fixture providing a mesh with a 32-edge boundary loop exceeding repair threshold."""
    from tests.fixtures.mesh_fixtures import create_large_hole_mesh, save_fixture_mesh
    mesh = create_large_hole_mesh(32)
    return save_fixture_mesh(mesh, tmp_path / "large_hole.obj", "obj")


@pytest.fixture
def duplicate_geom_obj(tmp_path: Path) -> Path:
    """Fixture providing a mesh with duplicate faces and floating vertices."""
    from tests.fixtures.mesh_fixtures import create_duplicate_and_unreferenced_mesh, save_fixture_mesh
    mesh = create_duplicate_and_unreferenced_mesh()
    return save_fixture_mesh(mesh, tmp_path / "duplicate_geom.obj", "obj")

