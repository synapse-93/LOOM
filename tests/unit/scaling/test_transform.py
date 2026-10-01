"""Unit tests for ScaleTransformer and deterministic vertex scaling."""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest
import trimesh

from loom.scaling.transform import ScaleTransformer
from tests.fixtures.mesh_fixtures import create_clean_cube


def test_vertex_transformation_global_origin() -> None:
    """Verify deterministic vertex transformation around default global origin (0, 0, 0)."""
    vertices = np.array([
        [10.0, 20.0, 30.0],
        [0.0, 0.0, 0.0],
        [-5.0, 15.0, -25.0],
    ])
    scaled = ScaleTransformer.transform_vertices(vertices, scale_factor=2.0, origin=(0.0, 0.0, 0.0))

    np.testing.assert_allclose(
        scaled,
        [
            [20.0, 40.0, 60.0],
            [0.0, 0.0, 0.0],
            [-10.0, 30.0, -50.0],
        ],
    )


def test_vertex_transformation_custom_origin() -> None:
    """Verify deterministic vertex transformation around explicit custom origin: origin + s * (p - origin)."""
    origin = (10.0, 20.0, 30.0)
    vertices = np.array([
        [15.0, 20.0, 30.0],  # 5 units away in X
        [10.0, 20.0, 30.0],  # At the origin
        [10.0, 25.0, 30.0],  # 5 units away in Y
    ])
    scaled = ScaleTransformer.transform_vertices(vertices, scale_factor=3.0, origin=origin)

    np.testing.assert_allclose(
        scaled,
        [
            [25.0, 20.0, 30.0],  # 10 + 3 * (15 - 10) = 25
            [10.0, 20.0, 30.0],  # 10 + 3 * (10 - 10) = 10
            [10.0, 35.0, 30.0],  # 20 + 3 * (25 - 20) = 35
        ],
    )


def test_mesh_topology_preservation() -> None:
    """Verify that transform_mesh keeps faces, face indices, and vertex count 100% identical."""
    cube = create_clean_cube()
    initial_v_count = len(cube.vertices)
    initial_f_count = len(cube.faces)
    initial_faces = np.copy(cube.faces)

    transformer = ScaleTransformer()
    scaled_cube = transformer.transform_mesh(cube, scale_factor=2.5)

    assert len(scaled_cube.vertices) == initial_v_count
    assert len(scaled_cube.faces) == initial_f_count
    np.testing.assert_array_equal(scaled_cube.faces, initial_faces)


def test_apply_scale_file_roundtrip(tmp_path: Path) -> None:
    """Verify loading, scaling, and saving mesh file."""
    cube = create_clean_cube()
    in_mesh = tmp_path / "cube.obj"
    cube.export(str(in_mesh))

    out_mesh = tmp_path / "scaled_cube.obj"
    transformer = ScaleTransformer()
    res_path = transformer.apply_scale(in_mesh, scale_factor=2.0, output_path=out_mesh)

    assert res_path.is_file()
    reloaded = trimesh.load(str(res_path), process=False)
    # Original cube width 2.0 -> scaled width 4.0
    extents = reloaded.extents
    np.testing.assert_allclose(extents, [4.0, 4.0, 4.0], rtol=1e-5)


def test_scale_transformer_rejection_invalid_values() -> None:
    """Verify ScaleTransformer rejects zero, negative, and non-finite scale factors."""
    verts = np.array([[1.0, 2.0, 3.0]])

    with pytest.raises(ValueError):
        ScaleTransformer.transform_vertices(verts, scale_factor=0.0)

    with pytest.raises(ValueError):
        ScaleTransformer.transform_vertices(verts, scale_factor=-1.0)

    with pytest.raises(ValueError):
        ScaleTransformer.transform_vertices(verts, scale_factor=float("nan"))

    with pytest.raises(ValueError):
        ScaleTransformer.transform_vertices(verts, scale_factor=float("inf"))

    with pytest.raises(ValueError):
        ScaleTransformer.transform_vertices(verts, scale_factor=2.0, origin=(0.0, float("nan"), 0.0))
