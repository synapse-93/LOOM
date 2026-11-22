"""CPU unit tests for Masked TSDF volumetric fusion & Marching Cubes (tsdf_mesh.py)."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import trimesh

from loom.reconstruction.tsdf_mesh import (
    TsdfExtractionConfig,
    TsdfMeshExtractor,
    compute_foreground_bounding_sphere,
    mask_depth_map,
)


def _render_synthetic_sphere_view(
    cam_pos: np.ndarray,
    radius: float = 0.5,
    width: int = 96,
    height: int = 96,
    focal: float = 96.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Analytically ray-cast a unit-centered sphere from ``cam_pos`` looking at origin."""
    forward = -cam_pos / np.linalg.norm(cam_pos)
    up_hint = np.array([0.0, 0.0, 1.0]) if abs(forward[2]) < 0.95 else np.array([0.0, 1.0, 0.0])
    right = np.cross(forward, up_hint)
    right /= np.linalg.norm(right)
    down = np.cross(forward, right)

    # World-to-camera R, t (OpenCV convention: +X right, +Y down, +Z forward)
    R = np.vstack([right, down, forward])
    t = -R @ cam_pos
    extrinsic = np.eye(4, dtype=np.float64)
    extrinsic[:3, :3] = R
    extrinsic[:3, 3] = t

    cx, cy = width / 2.0, height / 2.0
    K = np.array([[focal, 0.0, cx], [0.0, focal, cy], [0.0, 0.0, 1.0]], dtype=np.float64)

    xs, ys = np.meshgrid(np.arange(width, dtype=np.float64), np.arange(height, dtype=np.float64))
    ray_cam = np.stack([(xs - cx) / focal, (ys - cy) / focal, np.ones_like(xs)], axis=-1)
    ray_dirs = ray_cam @ R  # world ray directions (unnormalized along z_cam = 1)
    ray_norms = np.linalg.norm(ray_dirs, axis=-1)
    ray_unit = ray_dirs / ray_norms[..., None]

    # Ray-sphere intersection |cam_pos + s * d|^2 = r^2
    b = 2.0 * np.sum(ray_unit * cam_pos[None, None, :], axis=-1)
    c = float(np.dot(cam_pos, cam_pos) - radius * radius)
    disc = b * b - 4.0 * c

    hit = disc > 0.0
    depth = np.zeros((height, width), dtype=np.float32)
    mask = np.zeros((height, width), dtype=np.uint8)
    alpha = np.zeros((height, width), dtype=np.float32)

    s_hit = (-b[hit] - np.sqrt(disc[hit])) * 0.5
    # Convert ray distance s to camera Z-depth: z_cam = s / ||ray_cam||
    z_depth = s_hit / ray_norms[hit]
    depth[hit] = z_depth.astype(np.float32)
    mask[hit] = 255
    alpha[hit] = 1.0

    # Inject background depth noise outside the mask to prove masking prevents leakage
    depth[~hit] = 2.0
    rgb = np.full((height, width, 3), 180, dtype=np.uint8)
    return depth, rgb, mask, alpha, K, extrinsic


def test_mask_depth_map_zeroes_background_and_low_alpha() -> None:
    """Verify render_alpha>=0.45 protects against gt_mask voids while zeroing low-alpha background,
    and gt_mask still clips when render_alpha is absent."""
    depth = np.full((4, 4), 1.5, dtype=np.float32)
    mask = np.full((4, 4), 255, dtype=np.uint8)
    mask[0, :] = 0  # simulated noisy isnet dropout on row 0
    alpha = np.full((4, 4), 0.9, dtype=np.float32)
    alpha[:, 0] = 0.2  # low-alpha background column 0

    # With render_alpha provided (default skip_gt_mask_when_alpha_present=True):
    # row 0 survives because render_alpha=0.9 >= 0.45, while column 0 is strictly zeroed.
    masked_alpha = mask_depth_map(depth, gt_mask=mask, render_alpha=alpha, alpha_threshold=0.45)
    assert np.all(masked_alpha[:, 0] == 0.0)
    assert np.all(masked_alpha[:, 1:] == 1.5)

    # Without render_alpha: gt_mask==0 strictly zeroes row 0
    masked_gt = mask_depth_map(depth, gt_mask=mask, render_alpha=None)
    assert np.all(masked_gt[0, :] == 0.0)
    assert np.all(masked_gt[1:, :] == 1.5)

    # Verify Phase 4 TSDF defaults (voxel_divisor=320, trunc=2.5, alpha_threshold=0.45)
    cfg = TsdfExtractionConfig()
    assert cfg.voxel_divisor == 320.0
    assert cfg.trunc_voxel_multiplier == 2.5
    assert cfg.alpha_threshold == 0.45


def test_compute_foreground_bounding_sphere_ignores_outliers() -> None:
    """Verify 5th-95th percentile bounding sphere rejects far outliers, low-opacity surfels, and clamps max_radius."""
    rng = np.random.default_rng(7)
    core = rng.uniform(-0.5, 0.5, size=(500, 3))
    outliers = np.array([[50.0, 50.0, 50.0], [-50.0, -50.0, -50.0]])
    pts = np.vstack([core, outliers])
    opacities = np.concatenate([np.full(500, 0.9), np.full(2, 0.05)])

    center, radius = compute_foreground_bounding_sphere(pts, opacities=opacities, min_opacity=0.35)
    assert np.linalg.norm(center) < 0.1
    assert 0.5 < radius < 1.0

    # Verify max_radius clamping (<= 1.35 * object_radius)
    _, clamped_radius = compute_foreground_bounding_sphere(
        pts, opacities=opacities, min_opacity=0.35, max_radius=0.6
    )
    assert np.isclose(clamped_radius, 0.6)


def test_tsdf_mesh_extractor_fuses_synthetic_sphere_into_valid_mesh(tmp_path: Path) -> None:
    """Fuse analytical multi-view sphere depth maps via Open3D ScalableTSDFVolume -> valid mesh."""
    depths, rgbs, masks, alphas, Ks, extrinsics = [], [], [], [], [], []
    sphere_r = 0.5
    cam_dist = 1.8

    # 18 views across 2 elevation rings + poles for full sphere coverage
    cam_positions = []
    for elev_deg in (-30.0, 0.0, 35.0):
        elev = math.radians(elev_deg)
        for az_deg in range(0, 360, 60):
            az = math.radians(az_deg)
            cam_positions.append(
                np.array([
                    cam_dist * math.cos(elev) * math.cos(az),
                    cam_dist * math.cos(elev) * math.sin(az),
                    cam_dist * math.sin(elev),
                ])
            )
    cam_positions.append(np.array([0.0, 0.0, cam_dist]))
    cam_positions.append(np.array([0.0, 0.0, -cam_dist]))

    for cam_pos in cam_positions:
        d, rgb, m, a, K, ext = _render_synthetic_sphere_view(cam_pos, radius=sphere_r)
        depths.append(d)
        rgbs.append(rgb)
        masks.append(m)
        alphas.append(a)
        Ks.append(K)
        extrinsics.append(ext)

    out_ply = tmp_path / "mesh_2dgs_raw.ply"
    extractor = TsdfMeshExtractor(TsdfExtractionConfig(voxel_divisor=32.0))
    res = extractor.fuse_depth_maps(
        depth_maps=depths,
        rgb_maps=rgbs,
        intrinsics=Ks,
        extrinsics=extrinsics,
        output_path=out_ply,
        bounding_center=np.zeros(3),
        bounding_radius=sphere_r,
        masks=masks,
        alphas=alphas,
    )

    assert res.mesh_path == out_ply.resolve()
    assert out_ply.is_file()
    assert res.views_fused == len(cam_positions)
    assert res.vertex_count > 100
    assert res.face_count > 200
    assert np.isclose(res.voxel_length, sphere_r / 32.0)
    assert np.isclose(res.sdf_trunc, 2.5 * res.voxel_length)

    loaded = trimesh.load(str(out_ply), process=False)
    assert isinstance(loaded, trimesh.Trimesh)
    # Reconstructed sphere diameter should closely match 2 * sphere_r = 1.0
    assert np.allclose(loaded.extents, [1.0, 1.0, 1.0], atol=0.15)

