"""Unit tests for printability checkers and validation gate enforcement."""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest
import trimesh

from loom.printability.exceptions import PrintabilityValidationError
from loom.printability.gate import PrintabilityGate
from loom.printability.manifold import ManifoldChecker
from loom.printability.watertight import WatertightChecker
from tests.fixtures.mesh_fixtures import create_clean_cube


def _create_open_cube() -> trimesh.Trimesh:
    """Create a cube missing one face (open boundary)."""
    cube = create_clean_cube()
    # Remove the first face
    return trimesh.Trimesh(vertices=cube.vertices, faces=cube.faces[1:], process=False)


def _create_non_manifold_edge_mesh() -> trimesh.Trimesh:
    """Create a mesh with an edge shared by 3 faces (T-junction)."""
    verts = np.array([
        [0.0, 0.0, 0.0],  # 0
        [1.0, 0.0, 0.0],  # 1 (edge 0-1 is shared)
        [0.0, 1.0, 0.0],  # 2
        [0.0, -1.0, 0.0], # 3
        [0.0, 0.0, 1.0],  # 4
    ], dtype=np.float64)
    faces = np.array([
        [0, 1, 2],  # face 1 shares edge (0, 1)
        [0, 1, 3],  # face 2 shares edge (0, 1)
        [0, 1, 4],  # face 3 shares edge (0, 1) -> 3 faces on one edge!
    ])
    return trimesh.Trimesh(vertices=verts, faces=faces, process=False)


def _create_pinched_vertex_mesh() -> trimesh.Trimesh:
    """Create two closed tetrahedra meeting at a single pinched apex vertex."""
    verts = np.array([
        [0.0, 0.0, 0.0],       # 0 (shared pinched apex)
        [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0],       # tet 1 (1, 2, 3)
        [-1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, -1.0],   # tet 2 (4, 5, 6)
    ], dtype=np.float64)
    faces = np.array([
        [0, 1, 2], [0, 2, 3], [0, 3, 1], [1, 3, 2],  # tet 1 (closed)
        [0, 4, 5], [0, 5, 6], [0, 6, 4], [4, 6, 5],  # tet 2 (closed)
    ])
    return trimesh.Trimesh(vertices=verts, faces=faces, process=False)


def test_watertight_checker_closed_vs_open_mesh() -> None:
    """Verify WatertightChecker identifies boundary edges and calculates volume accurately."""
    checker = WatertightChecker()
    cube = create_clean_cube()

    # Closed cube
    assert checker.get_boundary_edge_count(cube) == 0
    assert checker.get_volume(cube) == pytest.approx(8.0)
    assert checker.is_watertight(cube) is True

    # Open cube
    open_cube = _create_open_cube()
    assert checker.get_boundary_edge_count(open_cube) > 0
    assert checker.is_watertight(open_cube) is False


def test_manifold_checker_edge_and_vertex_manifolds() -> None:
    """Verify ManifoldChecker detects non-manifold edges and pinched vertices."""
    checker = ManifoldChecker()
    cube = create_clean_cube()

    # Clean manifold cube
    assert checker.is_edge_manifold(cube) is True
    assert checker.is_vertex_manifold(cube) is True
    assert checker.is_manifold(cube) is True

    # Non-manifold edge
    edge_mesh = _create_non_manifold_edge_mesh()
    assert checker.get_non_manifold_edge_count(edge_mesh) == 1
    assert checker.is_edge_manifold(edge_mesh) is False
    assert checker.is_manifold(edge_mesh) is False

    # Non-manifold pinched vertex
    pinched_mesh = _create_pinched_vertex_mesh()
    assert checker.get_non_manifold_vertex_count(pinched_mesh) == 1
    assert checker.is_vertex_manifold(pinched_mesh) is False
    assert checker.is_manifold(pinched_mesh) is False


def test_printability_gate_passes_valid_geometry() -> None:
    """Verify PrintabilityGate passes valid closed 2-manifold mesh with positive volume."""
    gate = PrintabilityGate()
    cube = create_clean_cube()

    result = gate.validate(cube)
    assert result.passed is True
    assert result.is_watertight is True
    assert result.is_manifold is True
    assert result.is_positive_volume is True
    assert result.boundary_edge_count == 0
    assert result.non_manifold_edge_count == 0
    assert result.non_manifold_vertex_count == 0
    assert result.volume_mm3 == pytest.approx(8.0)
    assert len(result.errors) == 0


def test_printability_gate_rejection_and_enforcement() -> None:
    """Verify PrintabilityGate rejects invalid meshes and enforce_gate raises PrintabilityValidationError."""
    gate = PrintabilityGate()

    # Open mesh
    open_cube = _create_open_cube()
    res_open = gate.validate(open_cube)
    assert res_open.passed is False
    assert any("boundary edges" in err.lower() for err in res_open.errors)

    with pytest.raises(PrintabilityValidationError, match="boundary edges"):
        gate.enforce_gate(open_cube)

    # Non-manifold edge mesh
    nm_edge = _create_non_manifold_edge_mesh()
    res_edge = gate.validate(nm_edge)
    assert res_edge.passed is False
    assert any("non-manifold edges" in err.lower() for err in res_edge.errors)

    with pytest.raises(PrintabilityValidationError, match="non-manifold edges"):
        gate.enforce_gate(nm_edge)

