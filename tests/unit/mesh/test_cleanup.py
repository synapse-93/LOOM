"""Unit tests for MeshCleaner."""

from __future__ import annotations

import numpy as np
import pytest
import trimesh

from loom.config.models import MeshConfig
from loom.mesh.cleanup import MeshCleaner
from tests.fixtures.mesh_fixtures import (
    create_clean_cube,
    create_degenerate_mesh,
    create_duplicate_and_unreferenced_mesh,
)


def test_clean_mesh_remains_geometrically_stable() -> None:
    """Verify that a clean watertight mesh is unchanged by cleanup."""
    mesh = create_clean_cube()
    cleaner = MeshCleaner(MeshConfig())
    cleaned_mesh, action = cleaner.clean_mesh(mesh)

    assert action.vertices_before == 8
    assert action.vertices_after == 8
    assert action.faces_before == 12
    assert action.faces_after == 12
    assert action.degenerate_faces_removed == 0
    assert action.duplicate_faces_removed == 0
    assert action.unreferenced_vertices_removed == 0
    assert np.allclose(mesh.vertices, cleaned_mesh.vertices)


def test_cleanup_degenerate_faces() -> None:
    """Verify that zero-area degenerate triangles are removed."""
    mesh = create_degenerate_mesh()
    cleaner = MeshCleaner(MeshConfig(remove_degenerate_faces=True))
    cleaned_mesh, action = cleaner.clean_mesh(mesh)

    assert action.degenerate_faces_removed >= 1
    assert action.faces_after == 12
    assert len(cleaned_mesh.faces) == 12


def test_cleanup_duplicate_and_unreferenced_geometry() -> None:
    """Verify that duplicate faces and unreferenced floating vertices are removed."""
    mesh = create_duplicate_and_unreferenced_mesh()
    cleaner = MeshCleaner(MeshConfig(
        remove_duplicate_faces=True,
        remove_unreferenced_vertices=True,
    ))
    cleaned_mesh, action = cleaner.clean_mesh(mesh)

    assert action.duplicate_faces_removed >= 1
    assert action.unreferenced_vertices_removed == 2
    assert action.faces_after == 12
    assert action.vertices_after == 8


def test_cleanup_nan_vertices() -> None:
    """Verify that NaN vertices and faces referencing them are purged."""
    v = np.array([
        [-1.0, -1.0, -1.0],
        [ 1.0, -1.0, -1.0],
        [ 1.0,  1.0, -1.0],
        [np.nan, 0.0, 0.0],  # Invalid
    ])
    f = np.array([
        [0, 1, 2],
        [0, 1, 3],  # References NaN vertex
    ])
    mesh = trimesh.Trimesh(vertices=v, faces=f, process=False)
    cleaner = MeshCleaner(MeshConfig())
    cleaned_mesh, action = cleaner.clean_mesh(mesh)

    assert action.invalid_vertices_removed == 1
    assert action.faces_after == 1
    assert len(cleaned_mesh.vertices) == 3


def test_cleanup_invalid_face_indices() -> None:
    """Verify that faces with out-of-bounds indices are removed."""
    v = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
    ])
    f = np.array([
        [0, 1, 2],
        [0, 1, 99],  # Out of bounds
    ])
    mesh = trimesh.Trimesh(vertices=v, faces=f, process=False)
    cleaner = MeshCleaner(MeshConfig())
    cleaned_mesh, action = cleaner.clean_mesh(mesh)

    assert action.invalid_faces_removed == 1
    assert len(cleaned_mesh.faces) == 1
