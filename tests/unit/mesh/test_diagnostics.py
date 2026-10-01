"""Unit tests for MeshDiagnostics (read-only geometry and topology diagnostics)."""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest
import trimesh

from loom.mesh.diagnostics import MeshDiagnostics
from loom.mesh.exceptions import MeshInvalidError, MeshLoadError
from tests.fixtures.mesh_fixtures import (
    create_clean_cube,
    create_disconnected_mesh,
    create_degenerate_mesh,
    create_hole_mesh,
    create_duplicate_and_unreferenced_mesh,
    save_fixture_mesh,
)


def test_diagnostics_clean_cube() -> None:
    """Verify diagnostics on a clean watertight cube."""
    mesh = create_clean_cube()
    diag = MeshDiagnostics.inspect(mesh)

    assert diag.vertex_count == 8
    assert diag.face_count == 12
    assert diag.component_count == 1
    assert diag.boundary_edge_count == 0
    assert diag.boundary_loop_count == 0
    assert diag.is_watertight is True
    assert diag.has_nan_or_inf is False
    assert diag.degenerate_face_count == 0
    assert diag.duplicate_face_count == 0
    assert diag.unreferenced_vertex_count == 0
    assert diag.volume is not None
    assert abs(diag.volume - 8.0) < 1e-4
    assert diag.surface_area is not None
    assert abs(diag.surface_area - 24.0) < 1e-4
    assert tuple(diag.extents) == (2.0, 2.0, 2.0)
    assert diag.status == "VALID"

    assert len(diag.errors) == 0


def test_diagnostics_disconnected_mesh() -> None:
    """Verify diagnostics detects multiple components."""
    mesh = create_disconnected_mesh()
    diag = MeshDiagnostics.inspect(mesh)

    assert diag.component_count == 2
    assert diag.vertex_count == 12
    assert diag.face_count == 16
    assert diag.is_watertight is True
    assert diag.status in ("VALID", "WARNING")


def test_diagnostics_degenerate_mesh() -> None:
    """Verify diagnostics detects collinear/zero-area degenerate faces."""
    mesh = create_degenerate_mesh()
    diag = MeshDiagnostics.inspect(mesh)

    assert diag.degenerate_face_count >= 1
    assert any("degenerate" in w.lower() for w in diag.warnings)
    assert diag.status == "WARNING"


def test_diagnostics_hole_mesh() -> None:
    """Verify diagnostics detects boundary defects and lack of watertightness."""
    mesh = create_hole_mesh()
    diag = MeshDiagnostics.inspect(mesh)

    assert diag.face_count == 11
    assert diag.boundary_edge_count == 3
    assert diag.boundary_loop_count == 1
    assert diag.is_watertight is False
    assert any("boundary" in w.lower() or "open" in w.lower() for w in diag.warnings)
    assert diag.status == "WARNING"


def test_diagnostics_duplicate_and_unreferenced_mesh() -> None:
    """Verify diagnostics detects duplicate faces and unreferenced vertices."""
    mesh = create_duplicate_and_unreferenced_mesh()
    diag = MeshDiagnostics.inspect(mesh)

    assert diag.duplicate_face_count >= 1
    assert diag.unreferenced_vertex_count == 2
    assert any("duplicate" in w.lower() for w in diag.warnings)
    assert any("unreferenced" in w.lower() for w in diag.warnings)


def test_diagnostics_nan_vertices() -> None:
    """Verify diagnostics detects NaN coordinates and sets ERROR status."""
    v = np.array([
        [0.0, 0.0, 0.0],
        [1.0, np.nan, 0.0],
        [0.0, 1.0, 0.0],
    ])
    f = np.array([[0, 1, 2]])
    mesh = trimesh.Trimesh(vertices=v, faces=f, process=False)
    diag = MeshDiagnostics.inspect(mesh)

    assert diag.has_nan_or_inf is True
    assert diag.status == "ERROR"
    assert any("nan" in e.lower() for e in diag.errors)


def test_diagnostics_from_file_formats(tmp_path: Path) -> None:
    """Verify inspect_file correctly loads and analyzes OBJ, PLY, and STL."""
    clean = create_clean_cube()
    for fmt in ["obj", "ply", "stl"]:
        p = save_fixture_mesh(clean, tmp_path / f"cube.{fmt}", fmt)
        diag = MeshDiagnostics.inspect_file(p)
        assert diag.vertex_count > 0
        assert diag.face_count == 12
        if fmt in ("obj", "ply"):
            assert diag.status == "VALID"
        else:
            assert diag.status in ("VALID", "WARNING")



def test_diagnostics_missing_file_raises(tmp_path: Path) -> None:
    """Verify inspect_file raises FileNotFoundError for missing file."""
    with pytest.raises(FileNotFoundError):
        MeshDiagnostics.inspect_file(tmp_path / "nonexistent.obj")


def test_diagnostics_to_dict_serializable() -> None:
    """Verify diagnostics serializes to a clean Python dictionary."""
    mesh = create_clean_cube()
    diag = MeshDiagnostics.inspect(mesh)
    d = diag.to_dict()

    assert isinstance(d, dict)
    assert d["vertex_count"] == 8
    assert d["face_count"] == 12
    assert d["is_watertight"] is True
    assert d["status"] == "VALID"
