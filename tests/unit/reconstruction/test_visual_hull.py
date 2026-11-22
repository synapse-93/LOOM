"""CPU unit tests for VisualHullFilter (src/loom/reconstruction/visual_hull.py)."""

from __future__ import annotations

import math
import struct
from pathlib import Path

import cv2
import numpy as np

from loom.reconstruction.visual_hull import VisualHullConfig, VisualHullFilter


def _rotmat_to_qvec(R: np.ndarray) -> np.ndarray:
    """Convert 3x3 rotation matrix to COLMAP quaternion [qw, qx, qy, qz]."""
    trace = float(np.trace(R))
    if trace > 0.0:
        s = 0.5 / math.sqrt(trace + 1.0)
        qw = 0.25 / s
        qx = (R[2, 1] - R[1, 2]) * s
        qy = (R[0, 2] - R[2, 0]) * s
        qz = (R[1, 0] - R[0, 1]) * s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
        qw = (R[2, 1] - R[1, 2]) / s
        qx = 0.25 * s
        qy = (R[0, 1] + R[1, 0]) / s
        qz = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = 2.0 * math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
        qw = (R[0, 2] - R[2, 0]) / s
        qx = (R[0, 1] + R[1, 0]) / s
        qy = 0.25 * s
        qz = (R[1, 2] + R[2, 1]) / s
    else:
        s = 2.0 * math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
        qw = (R[1, 0] - R[0, 1]) / s
        qx = (R[0, 2] + R[2, 0]) / s
        qy = (R[1, 2] + R[2, 1]) / s
        qz = 0.25 * s
    q = np.array([qw, qx, qy, qz], dtype=np.float64)
    return q / np.linalg.norm(q)


def _write_undistorted_pinhole_scene(
    root: Path,
    points_xyz: np.ndarray,
    points_rgb: np.ndarray,
    *,
    num_views: int = 12,
    orbit_radius: float = 3.5,
    img_size: int = 128,
    focal: float = 128.0,
    mask_radius_px: int = 18,
) -> tuple[Path, Path, list[str]]:
    """Write synthetic undistorted dense/sparse/{cameras,images,points3D}.bin + binary masks."""
    sparse_dir = root / "dense" / "sparse"
    masks_dir = root / "masks"
    sparse_dir.mkdir(parents=True)
    masks_dir.mkdir(parents=True)

    # 1. cameras.bin (1 PINHOLE camera, model_id=1)
    with open(sparse_dir / "cameras.bin", "wb") as f:
        f.write(struct.pack("<Q", 1))
        f.write(struct.pack("<IiQQ", 1, 1, img_size, img_size))
        f.write(struct.pack("<4d", focal, focal, img_size / 2.0, img_size / 2.0))

    # 2. images.bin + corresponding centered foreground masks
    view_names: list[str] = []
    angles = np.linspace(0.0, 2.0 * np.pi, num_views, endpoint=False)
    with open(sparse_dir / "images.bin", "wb") as f:
        f.write(struct.pack("<Q", num_views))
        for idx, ang in enumerate(angles, start=1):
            cam_pos = np.array([orbit_radius * math.cos(ang), orbit_radius * math.sin(ang), 0.3])
            forward = -cam_pos / np.linalg.norm(cam_pos)
            right = np.cross(forward, np.array([0.0, 0.0, 1.0]))
            right /= np.linalg.norm(right)
            down = np.cross(forward, right)
            R = np.vstack([right, down, forward])
            t = -R @ cam_pos
            qvec = _rotmat_to_qvec(R)

            fname = f"frame_{idx:04d}.jpg"
            view_names.append(fname)
            f.write(struct.pack("<I", idx))
            f.write(struct.pack("<4d", *qvec))
            f.write(struct.pack("<3d", *t))
            f.write(struct.pack("<I", 1))
            f.write(fname.encode("utf-8") + b"\x00")
            f.write(struct.pack("<Q", 0))  # 0 points2D

            mask = np.zeros((img_size, img_size), dtype=np.uint8)
            cv2.circle(mask, (img_size // 2, img_size // 2), mask_radius_px, 255, -1)
            cv2.imwrite(str(masks_dir / f"frame_{idx:04d}.png"), mask)

    # 3. points3D.bin
    with open(sparse_dir / "points3D.bin", "wb") as f:
        f.write(struct.pack("<Q", len(points_xyz)))
        for pid, (xyz, rgb) in enumerate(zip(points_xyz, points_rgb), start=1):
            f.write(struct.pack("<Q", pid))
            f.write(struct.pack("<3d", float(xyz[0]), float(xyz[1]), float(xyz[2])))
            f.write(struct.pack("<3B", int(rgb[0]), int(rgb[1]), int(rgb[2])))
            f.write(struct.pack("<d", 0.1))
            f.write(struct.pack("<Q", 0))

    return sparse_dir, masks_dir, view_names


def test_visual_hull_rejects_background_wall_and_recovers_tight_object_radius(tmp_path: Path) -> None:
    """Verify >=70% multi-view visual-hull rule rejects background points hitting 2-3 masks
    and computes tight object_radius (~0.25) instead of room orbit radius (~3.5)."""
    rng = np.random.default_rng(42)

    # 650 true foreground points in a sphere of radius 0.25 around origin
    dirs = rng.normal(size=(650, 3))
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    radii = 0.25 * np.cbrt(rng.uniform(0.0, 1.0, size=(650, 1)))
    fg_pts = dirs * radii

    # 300 background wall points at x ~ 1.2 (pass behind the centered silhouette in ~2-3/12 views!)
    wall_pts = np.column_stack([
        rng.uniform(1.0, 1.4, size=300),
        rng.uniform(-0.15, 0.15, size=300),
        rng.uniform(-0.15, 0.15, size=300),
    ])

    all_pts = np.vstack([fg_pts, wall_pts])
    all_rgb = np.vstack([
        np.full((len(fg_pts), 3), [40, 200, 80], dtype=np.uint8),
        np.full((len(wall_pts), 3), [200, 40, 40], dtype=np.uint8),
    ])

    sparse_dir, masks_dir, view_names = _write_undistorted_pinhole_scene(
        tmp_path,
        all_pts,
        all_rgb,
        num_views=12,
        orbit_radius=3.5,
    )

    out_ply = tmp_path / "debug_masks" / "visual_hull_points.ply"
    vh = VisualHullFilter(VisualHullConfig(min_visible_views=8, min_fg_ratio=0.70, min_surviving_points=500))
    res = vh.run(
        undistorted_sparse_dir=sparse_dir,
        masks_dir=masks_dir,
        output_ply_path=out_ply,
        valid_view_names=view_names,
    )

    assert res.total_sparse_points == 950
    assert res.hit_ratio_threshold_used == 0.70
    # Background wall completely rejected; dense DBSCAN foreground core retained
    assert 600 <= res.foreground_points <= 650
    assert np.all(np.linalg.norm(res.points_xyz, axis=1) < 0.35)
    # Object radius tightly tracks ~0.25, while scene_radius reflects camera orbit ~3.5
    assert 0.18 <= res.object_radius <= 0.30
    assert res.scene_radius > 3.0
    assert np.linalg.norm(np.array(res.object_center)) < 0.05
    assert out_ply.is_file()
    assert out_ply.stat().st_size > 100


def test_visual_hull_dbscan_prunes_fringe_cluster_far_from_lookat_center(tmp_path: Path) -> None:
    """Verify DBSCAN core clustering around camera-ray convergence point drops off-center fringe clusters."""
    rng = np.random.default_rng(99)

    # 600 core object points tightly centered at origin (r <= 0.20)
    core_pts = rng.uniform(-0.15, 0.15, size=(600, 3))
    # 250 off-center fringe clutter points clustered around [0.95, 0, 0] (disconnected from core)
    fringe_pts = rng.uniform(-0.08, 0.08, size=(250, 3)) + np.array([0.95, 0.0, 0.0])

    all_pts = np.vstack([core_pts, fringe_pts])
    all_rgb = np.full((len(all_pts), 3), 180, dtype=np.uint8)

    # Wide mask so even the fringe cluster passes silhouette hit check — DBSCAN + lookat must strip it!
    sparse_dir, masks_dir, view_names = _write_undistorted_pinhole_scene(
        tmp_path,
        all_pts,
        all_rgb,
        num_views=12,
        orbit_radius=3.5,
        mask_radius_px=55,
    )

    out_ply = tmp_path / "debug_masks" / "visual_hull_points.ply"
    vh = VisualHullFilter(VisualHullConfig(min_visible_views=8, min_fg_ratio=0.70, min_surviving_points=500))
    res = vh.run(
        undistorted_sparse_dir=sparse_dir,
        masks_dir=masks_dir,
        output_ply_path=out_ply,
        valid_view_names=view_names,
    )

    # Only the centered 600-pt core cluster survives; off-center fringe cluster is pruned
    assert 550 <= res.foreground_points <= 600
    assert res.object_radius < 0.30
    assert np.linalg.norm(np.array(res.object_center)) < 0.05

