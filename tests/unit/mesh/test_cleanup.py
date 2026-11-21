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


def test_remove_floor_plane(tmp_path) -> None:
    """Verify that dominant horizontal floor plane is detected and removed via RANSAC."""
    # 1. Create a planar ground grid at Z = 0.0
    x = np.linspace(-4, 4, 15)
    y = np.linspace(-4, 4, 15)
    xx, yy = np.meshgrid(x, y)
    zz = np.zeros_like(xx)
    ground_verts = np.column_stack([xx.ravel(), yy.ravel(), zz.ravel()])
    ground_faces = []
    nx, ny = len(x), len(y)
    for i in range(nx - 1):
        for j in range(ny - 1):
            idx = i * ny + j
            ground_faces.append([idx, idx + 1, idx + ny])
            ground_faces.append([idx + 1, idx + ny + 1, idx + ny])
    ground_mesh = trimesh.Trimesh(vertices=ground_verts, faces=ground_faces, process=False)
    ground_face_count = len(ground_mesh.faces)

    # 2. Create an object resting on the ground: sphere elevated so bottom is at Z = 0.0
    sphere = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
    sphere.vertices[:, 2] += 1.0  # touches Z = 0.0
    sphere_face_count = len(sphere.faces)

    combined = trimesh.util.concatenate([ground_mesh, sphere])
    assert len(combined.faces) == ground_face_count + sphere_face_count

    output_ply = tmp_path / "04_floor_removed.ply"
    cleaned_mesh, stats = MeshCleaner.remove_floor_plane(
        mesh=combined,
        normal_tolerance_deg=20.0,
        bottom_percentile=0.15,
        output_path=output_ply,
    )

    assert stats["floor_detected"] is True
    assert stats["faces_removed"] == ground_face_count
    assert len(cleaned_mesh.faces) == sphere_face_count
    assert output_ply.is_file()
    assert output_ply.stat().st_size > 0


def test_isolate_target_component_centroid_proximity(tmp_path) -> None:
    """Verify component isolation selects target component near reference point over larger distant clutter."""
    # Target shoe/object near scene center (0, 0, 0) with fewer faces
    target = trimesh.creation.icosphere(subdivisions=1, radius=0.5)
    target_faces = len(target.faces)

    # Background clutter/wall with far more faces located far away at (15, 15, 0)
    clutter = trimesh.creation.icosphere(subdivisions=3, radius=1.0)
    clutter.vertices += np.array([15.0, 15.0, 0.0])
    clutter_faces = len(clutter.faces)

    assert clutter_faces > target_faces

    scene = trimesh.util.concatenate([target, clutter])

    output_ply = tmp_path / "isolated_target.ply"
    isolated, stats = MeshCleaner.isolate_target_component(
        mesh=scene,
        reference_point=(0.0, 0.0, 0.0),
        min_faces=20,
        output_path=output_ply,
    )

    assert stats["selected_faces"] == target_faces
    assert len(isolated.faces) == target_faces
    assert output_ply.is_file()


def test_component_analyzer_filter_centroid_proximity() -> None:
    """Verify MeshComponentAnalyzer supports centroid_proximity strategy via config."""
    from loom.mesh.components import MeshComponentAnalyzer

    target = trimesh.creation.icosphere(subdivisions=1, radius=0.5)
    clutter = trimesh.creation.icosphere(subdivisions=3, radius=1.0)
    clutter.vertices += np.array([20.0, 20.0, 0.0])

    scene = trimesh.util.concatenate([target, clutter])

    cfg = MeshConfig(
        component_strategy="centroid_proximity",
        reference_point=(0.0, 0.0, 0.0),
        min_component_faces=20,
    )
    filtered, action = MeshComponentAnalyzer.filter(scene, cfg)

    assert action.strategy == "centroid_proximity"
    assert len(filtered.faces) == len(target.faces)


def test_cull_mesh_by_point_cloud_distance(tmp_path: Path) -> None:
    """Verify that KDTree distance culling discards ungrounded mesh faces far from point cloud."""
    # 1. Ground truth object (cube) near origin
    cube = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    # Point cloud covering cube vertices with high density
    rng = np.random.default_rng(42)
    pc_points = rng.uniform(-0.5, 0.5, size=(1000, 3))

    # 2. Add an ungrounded floating bubble (balloon) far away at Z = 10.0
    balloon = trimesh.creation.icosphere(subdivisions=1, radius=0.5)
    balloon.vertices += np.array([0.0, 0.0, 10.0])

    combined_mesh = trimesh.util.concatenate([cube, balloon])
    total_faces = len(combined_mesh.faces)
    cube_faces = len(cube.faces)
    balloon_faces = len(balloon.faces)

    out_file = tmp_path / "culled.ply"
    culled, stats = MeshCleaner.cull_by_point_cloud_distance(
        mesh=combined_mesh,
        point_cloud=pc_points,
        multiplier=3.5,
        output_path=out_file,
    )

    assert stats["faces_removed"] == balloon_faces
    assert len(culled.faces) == cube_faces
    assert stats["threshold"] > 0
    assert stats["local_spacing"] > 0
    assert out_file.is_file()


def test_fit_floor_plane_ransac() -> None:
    """Verify that RANSAC horizontal plane fitting accurately estimates the ground plane."""
    # Plane at Z = 0.0 with noise + elevated object
    x = np.linspace(-2, 2, 10)
    y = np.linspace(-2, 2, 10)
    xx, yy = np.meshgrid(x, y)
    zz = np.zeros_like(xx)
    ground_verts = np.column_stack([xx.ravel(), yy.ravel(), zz.ravel()])
    faces = []
    for i in range(9):
        for j in range(9):
            idx = i * 10 + j
            faces.append([idx, idx + 1, idx + 10])
            faces.append([idx + 1, idx + 11, idx + 10])
    ground_mesh = trimesh.Trimesh(vertices=ground_verts, faces=faces, process=False)

    sphere = trimesh.creation.icosphere(subdivisions=1, radius=0.5)
    sphere.vertices += np.array([0.0, 0.0, 1.0])

    mesh = trimesh.util.concatenate([ground_mesh, sphere])
    normal, d, z_floor = MeshCleaner.fit_floor_plane_ransac(
        mesh,
        bottom_percentile=0.20,
        normal_tolerance_deg=15.0,
        distance_threshold=0.05,
    )

    assert normal is not None
    assert np.isclose(normal[2], 1.0, atol=0.05)
    assert np.isclose(z_floor, 0.0, atol=0.05)

