"""Unit tests for DimensionAnalyzer bounding box and oriented bounding box measurements."""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest
import trimesh

from loom.validation.dimensions import DimensionAnalyzer
from tests.fixtures.mesh_fixtures import create_clean_cube


def test_axis_aligned_bounding_box(tmp_path: Path) -> None:
    """Verify compute_bounding_box returns accurate AABB extents and dimensions."""
    cube = create_clean_cube()
    analyzer = DimensionAnalyzer()

    # Cube extents [-1, 1] in each dimension -> width=2.0, depth=2.0, height=2.0
    aabb = analyzer.compute_bounding_box(cube)
    assert aabb.width == pytest.approx(2.0)
    assert aabb.depth == pytest.approx(2.0)
    assert aabb.height == pytest.approx(2.0)
    assert aabb.volume == pytest.approx(8.0)
    assert aabb.dimensions == pytest.approx((2.0, 2.0, 2.0))


def test_oriented_bounding_box_dimensions_on_rotated_mesh(tmp_path: Path) -> None:
    """Verify compute_principal_dimensions computes exact OBB (Length, Width, Height) regardless of 3D orientation."""
    analyzer = DimensionAnalyzer()

    # Create box with known ground-truth principal dimensions: 100mm x 50mm x 20mm
    original_box = trimesh.creation.box(extents=[100.0, 50.0, 20.0])

    # Rotate box arbitrarily in 3D around non-principal axis
    R_rot = trimesh.transformations.rotation_matrix(np.pi / 4.0, [1.0, 1.0, 1.0])
    rotated_box = original_box.copy()
    rotated_box.apply_transform(R_rot)

    # AABB extents are expanded due to rotation
    aabb_extents = rotated_box.extents
    assert not np.allclose(aabb_extents, [100.0, 50.0, 20.0], atol=1.0)

    # OBB dimensions must recover ground-truth dimensions (Length >= Width >= Height)
    dims = analyzer.compute_principal_dimensions(rotated_box)
    length, width, height = dims

    assert length == pytest.approx(100.0, abs=1.0)
    assert width == pytest.approx(50.0, abs=1.0)
    assert height == pytest.approx(20.0, abs=1.0)
    assert length >= width >= height

    # Verify summary dict
    obb_dict = analyzer.compute_oriented_bounding_box(rotated_box)
    assert obb_dict["length_mm"] == pytest.approx(100.0, abs=1.0)
    assert obb_dict["width_mm"] == pytest.approx(50.0, abs=1.0)
    assert obb_dict["height_mm"] == pytest.approx(20.0, abs=1.0)
    assert obb_dict["volume_mm3"] == pytest.approx(100.0 * 50.0 * 20.0, rel=0.05)


def test_pca_fallback_on_planar_mesh() -> None:
    """Verify PCA fallback calculates principal dimensions on coplanar patch without networkx error."""
    analyzer = DimensionAnalyzer()

    # 2D rectangle in 3D: 40mm x 15mm
    verts = np.array([
        [0.0, 0.0, 0.0],
        [40.0, 0.0, 0.0],
        [40.0, 15.0, 0.0],
        [0.0, 15.0, 0.0],
    ], dtype=np.float64)
    faces = np.array([[0, 1, 2], [0, 2, 3]])
    mesh = trimesh.Trimesh(vertices=verts, faces=faces)

    dims = analyzer.compute_principal_dimensions(mesh)
    length, width, height = dims
    assert length == pytest.approx(40.0, abs=0.5)
    assert width == pytest.approx(15.0, abs=0.5)
    assert height == pytest.approx(0.0, abs=0.5)


def test_dimension_analyzer_file_errors(tmp_path: Path) -> None:
    """Verify analyzer raises FileNotFoundError for missing file and ValueError for empty mesh."""
    analyzer = DimensionAnalyzer()

    with pytest.raises(FileNotFoundError):
        analyzer.compute_principal_dimensions(tmp_path / "non_existent.obj")

    empty_mesh = trimesh.Trimesh()
    with pytest.raises(ValueError, match="0 vertices"):
        analyzer.compute_bounding_box(empty_mesh)

