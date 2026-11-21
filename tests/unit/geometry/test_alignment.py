"""Unit tests for Phase 4 Canonical Coordinate Frame Normalization."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import trimesh

from loom.geometry.alignment import AlignmentResult, CoordinateNormalizer, PlaneModel


def _create_synthetic_tilted_scene(
    plane_normal: np.ndarray,
    plane_point: np.ndarray,
    n_plane_pts: int = 2000,
    n_object_pts: int = 500,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate a planar ground surface with an object resting above it."""
    rng = np.random.default_rng(123)
    normal = plane_normal / np.linalg.norm(plane_normal)

    # Tangent vectors on plane
    ortho = np.array([1.0, 0.0, 0.0]) if abs(normal[0]) < 0.8 else np.array([0.0, 1.0, 0.0])
    u = np.cross(normal, ortho)
    u /= np.linalg.norm(u)
    v = np.cross(normal, u)

    # Random points on plane in range [-2, 2] x [-2, 2] with slight noise
    u_coords = rng.uniform(-2.0, 2.0, size=n_plane_pts)
    v_coords = rng.uniform(-2.0, 2.0, size=n_plane_pts)
    noise = rng.normal(0, 0.002, size=n_plane_pts)

    plane_pts = (
        plane_point[None, :]
        + u_coords[:, None] * u[None, :]
        + v_coords[:, None] * v[None, :]
        + noise[:, None] * normal[None, :]
    )

    # Object points strictly above the plane (along +normal direction)
    obj_u = rng.uniform(-0.5, 0.5, size=n_object_pts)
    obj_v = rng.uniform(-0.5, 0.5, size=n_object_pts)
    obj_h = rng.uniform(0.1, 1.0, size=n_object_pts)

    object_pts = (
        plane_point[None, :]
        + obj_u[:, None] * u[None, :]
        + obj_v[:, None] * v[None, :]
        + obj_h[:, None] * normal[None, :]
    )

    all_pts = np.vstack([plane_pts, object_pts])
    return all_pts, normal


def test_coordinate_normalizer_insufficient_points() -> None:
    """Verify that fewer than 3 points raises ValueError."""
    normalizer = CoordinateNormalizer()
    with pytest.raises(ValueError, match="Need at least 3 points"):
        normalizer.fit_support_plane_ransac(np.zeros((2, 3)))


def test_coordinate_normalizer_fit_plane() -> None:
    """Verify RANSAC plane fitting recovers tilted normal and points upward toward object mass."""
    # Tilted plane normal: 30 deg rotation around X axis
    true_normal = np.array([0.0, -0.5, np.sqrt(3) / 2.0])
    plane_pt = np.array([1.0, 2.0, 3.0])

    pts, normal = _create_synthetic_tilted_scene(true_normal, plane_pt)

    normalizer = CoordinateNormalizer(distance_threshold=0.015, max_iterations=500)
    plane = normalizer.fit_support_plane_ransac(pts)

    assert isinstance(plane, PlaneModel)
    assert len(plane.inlier_indices) >= 1800
    # Fitted normal should align with true normal
    dot = float(np.dot(plane.normal, true_normal))
    assert np.isclose(dot, 1.0, atol=0.05)


def test_coordinate_normalizer_numpy_array() -> None:
    """Verify normalizing a raw numpy array centers XY and places support plane at Z=0."""
    true_normal = np.array([0.2, 0.3, 0.9])
    true_normal /= np.linalg.norm(true_normal)
    plane_pt = np.array([5.0, -2.0, 1.0])

    pts, _ = _create_synthetic_tilted_scene(true_normal, plane_pt)

    normalizer = CoordinateNormalizer(distance_threshold=0.02, max_iterations=500)
    aligned_pts, result = normalizer.normalize(pts)

    assert isinstance(result, AlignmentResult)
    assert isinstance(aligned_pts, np.ndarray)
    assert aligned_pts.shape == pts.shape

    # Check that inlier points are now near Z = 0
    inlier_z = aligned_pts[result.support_plane.inlier_indices, 2]
    assert np.abs(np.median(inlier_z)) < 1e-3

    # Check that object points have positive Z
    non_inliers = np.setdiff1d(np.arange(len(pts)), result.support_plane.inlier_indices)
    assert np.mean(aligned_pts[non_inliers, 2]) > 0.1

    # Check XY center
    assert np.isclose(np.mean(aligned_pts[:, 0]), 0.0, atol=1e-3)
    assert np.isclose(np.mean(aligned_pts[:, 1]), 0.0, atol=1e-3)


def test_coordinate_normalizer_trimesh() -> None:
    """Verify normalizing a Trimesh geometry updates mesh vertices and transform."""
    # Create an icosphere resting on a tilted box
    box = trimesh.creation.box(extents=(4.0, 4.0, 0.1))
    sphere = trimesh.creation.icosphere(subdivisions=2, radius=0.5)
    sphere.vertices[:, 2] += 0.55  # rest on top of box

    mesh = trimesh.util.concatenate([box, sphere])

    # Tilt the entire scene
    rot = trimesh.transformations.rotation_matrix(np.radians(25.0), [1.0, 1.0, 0.0])
    mesh.apply_transform(rot)

    normalizer = CoordinateNormalizer(distance_threshold=0.02, max_iterations=500)
    aligned_mesh, result = normalizer.normalize(mesh)

    assert isinstance(aligned_mesh, trimesh.Trimesh)
    assert len(aligned_mesh.vertices) == len(mesh.vertices)
    assert len(aligned_mesh.faces) == len(mesh.faces)

    # Inlier plane should be at Z ~ 0
    inlier_z = aligned_mesh.vertices[result.support_plane.inlier_indices, 2]
    assert np.abs(np.median(inlier_z)) < 0.05

    # Rotated normal should be [0, 0, 1]
    rot_normal = result.rotation_matrix @ result.support_plane.normal
    assert np.allclose(rot_normal, [0.0, 0.0, 1.0], atol=1e-3)


def test_coordinate_normalizer_point_cloud() -> None:
    """Verify normalizing a PointCloud preserves colors and aligns coordinates."""
    pts = np.random.uniform(-1, 1, size=(500, 3))
    # Make points lie on plane z = 0 with a tilt
    pts[:400, 2] = 0.0
    colors = np.full((500, 4), 255, dtype=np.uint8)
    colors[:, 0] = 128

    pc = trimesh.PointCloud(vertices=pts, colors=colors)

    normalizer = CoordinateNormalizer(distance_threshold=0.01)
    aligned_pc, result = normalizer.normalize(pc)

    assert isinstance(aligned_pc, trimesh.PointCloud)
    assert len(aligned_pc.vertices) == 500
    assert hasattr(aligned_pc.visual, "vertex_colors")
    assert np.all(aligned_pc.visual.vertex_colors[:, 0] == 128)


def test_coordinate_normalizer_camera_centers_polarity() -> None:
    """Verify that camera_centers enforces upward polarity toward camera trajectory."""
    # Support plane at Z = 0
    rng = np.random.default_rng(99)
    plane_pts = rng.uniform(-1.0, 1.0, size=(1000, 3))
    plane_pts[:, 2] = 0.0  # exactly flat ground

    # Noise points scattered on both sides
    noise_pts = rng.uniform(-1.0, 1.0, size=(100, 3))
    all_pts = np.vstack([plane_pts, noise_pts])

    # Cameras strictly positioned above the ground (+Z)
    cam_centers = np.array([
        [0.0, 0.0, 5.0],
        [1.0, 1.0, 4.8],
        [-1.0, 0.5, 5.2],
    ])

    normalizer = CoordinateNormalizer(distance_threshold=0.01)
    plane = normalizer.fit_support_plane_ransac(all_pts, camera_centers=cam_centers)

    # Normal should point in +Z direction (toward cameras)
    assert plane.normal[2] > 0.95


def test_extract_colmap_camera_centers_nonexistent(tmp_path: Path) -> None:
    """Verify extract_colmap_camera_centers returns None gracefully for missing directory."""
    from loom.geometry.alignment import extract_colmap_camera_centers

    res = extract_colmap_camera_centers(tmp_path / "nonexistent")
    assert res is None


def test_ply_with_normals_io(tmp_path: Path) -> None:
    """Verify read_ply_with_normals and write_ply_with_normals round-trip correctly."""
    from loom.geometry.alignment import read_ply_with_normals, write_ply_with_normals

    pts = np.array([
        [1.0, 2.0, 3.0],
        [4.0, 5.0, 6.0],
        [7.0, 8.0, 9.0],
    ], dtype=np.float64)
    norms = np.array([
        [0.0, 0.0, 1.0],
        [0.0, 1.0, 0.0],
        [1.0, 0.0, 0.0],
    ], dtype=np.float64)
    colors = np.array([
        [255, 0, 0],
        [0, 255, 0],
        [0, 0, 255],
    ], dtype=np.uint8)

    out_file = tmp_path / "test_io.ply"
    write_ply_with_normals(out_file, pts, norms, colors)
    assert out_file.is_file()

    loaded_pts, loaded_norms, loaded_cols = read_ply_with_normals(out_file)
    assert np.allclose(loaded_pts, pts, atol=1e-5)
    assert np.allclose(loaded_norms, norms, atol=1e-5)
    assert loaded_cols is not None
    assert np.array_equal(loaded_cols, colors)


def test_coordinate_normalizer_steep_tilt_and_synchronous_normals(tmp_path: Path) -> None:
    """Verify full-cloud RANSAC recovers steeply tilted planes (where lowest 35% camera-Z fails)
    and synchronously rotates vertices and unit normal vectors via Rodrigues SO(3)."""
    from loom.geometry.alignment import read_ply_with_normals, write_ply_with_normals

    # Steeply tilted normal (~120 deg from +Z) with camera hemisphere in +true_normal direction
    true_normal = np.array([0.8, 0.3, -0.5])
    true_normal /= np.linalg.norm(true_normal)
    plane_pt = np.array([0.5, -1.0, 2.0])

    pts, _ = _create_synthetic_tilted_scene(true_normal, plane_pt, n_plane_pts=1500, n_object_pts=400)
    # Assign unit normals equal to true_normal for plane points, orthogonal for object points
    norms = np.tile(true_normal, (len(pts), 1))

    in_ply = tmp_path / "tilted_with_normals.ply"
    out_ply = tmp_path / "aligned_with_normals.ply"
    write_ply_with_normals(in_ply, pts, norms)

    cam_centers = np.array([
        plane_pt + 4.0 * true_normal,
        plane_pt + 4.5 * true_normal + np.array([0.5, -0.2, 0.1]),
    ])

    normalizer = CoordinateNormalizer(distance_threshold=0.015, max_iterations=1500)
    _, result = normalizer.normalize(in_ply, output_path=out_ply, camera_centers=cam_centers)

    # Check camera-centroid polarity: n . (C_cam - p0) > 0
    c_cam = np.mean(cam_centers, axis=0)
    p0 = -result.support_plane.d * result.support_plane.normal
    assert float(np.dot(result.support_plane.normal, c_cam - p0)) > 0.0

    # Check R is a proper SO(3) rotation (det == +1, R^T R == I)
    assert np.isclose(np.linalg.det(result.rotation_matrix), 1.0, atol=1e-6)
    assert np.allclose(result.rotation_matrix.T @ result.rotation_matrix, np.eye(3), atol=1e-6)

    # Check normals rotated synchronously to [0, 0, 1]
    assert result.aligned_normals is not None
    assert np.allclose(result.aligned_normals[0], [0.0, 0.0, 1.0], atol=0.05)
    assert np.allclose(np.linalg.norm(result.aligned_normals, axis=1), 1.0, atol=1e-6)

    # Check written PLY preserves rotated normals
    loaded_pts, loaded_norms, _ = read_ply_with_normals(out_ply)
    assert len(loaded_pts) == len(pts)
    assert np.allclose(loaded_norms[0], [0.0, 0.0, 1.0], atol=0.05)


def test_coordinate_normalizer_camera_centroid_flips_negative_hemisphere() -> None:
    """Verify camera_centers positioned on -Z side flips support plane normal to -Z."""
    rng = np.random.default_rng(77)
    plane_pts = rng.uniform(-1.0, 1.0, size=(1000, 3))
    plane_pts[:, 2] = 0.0
    noise_pts = rng.uniform(-1.0, 1.0, size=(100, 3))
    all_pts = np.vstack([plane_pts, noise_pts])

    cam_centers = np.array([
        [0.0, 0.0, -5.0],
        [0.5, -0.5, -4.5],
    ])

    normalizer = CoordinateNormalizer(distance_threshold=0.015, max_iterations=1000)
    plane = normalizer.fit_support_plane_ransac(all_pts, camera_centers=cam_centers)
    assert plane.normal[2] < -0.95



