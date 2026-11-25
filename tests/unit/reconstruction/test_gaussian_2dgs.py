"""CPU unit tests for Masked 2D Gaussian Splatting contracts, filtering, and VRAM caps."""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest

from loom.reconstruction.gaussian_2dgs import (
    Gaussian2DGSConfig,
    TrainingView,
    compose_debug_panel,
    compute_2dgs_loss,
    filter_sparse_points_by_masks,
    read_colmap_points3d_bin,
    scheduled_lambda_mask,
    scheduled_lambda_normal,
)


def _make_view(
    image_id: int,
    cam_pos: np.ndarray,
    mask_box: tuple[int, int, int, int],
    size: int = 100,
) -> TrainingView:
    forward = -cam_pos / np.linalg.norm(cam_pos)
    up_hint = np.array([0.0, 0.0, 1.0]) if abs(forward[2]) < 0.9 else np.array([0.0, 1.0, 0.0])
    right = np.cross(forward, up_hint)
    right /= np.linalg.norm(right)
    down = np.cross(forward, right)

    R = np.vstack([right, down, forward])
    t = -R @ cam_pos
    viewmat = np.eye(4, dtype=np.float64)
    viewmat[:3, :3] = R
    viewmat[:3, 3] = t

    K = np.array([[100.0, 0.0, size / 2.0], [0.0, 100.0, size / 2.0], [0.0, 0.0, 1.0]])
    mask = np.zeros((size, size), dtype=np.uint8)
    x0, y0, x1, y1 = mask_box
    mask[y0:y1, x0:x1] = 255
    rgb = np.zeros((size, size, 3), dtype=np.uint8)
    return TrainingView(
        image_id=image_id,
        name=f"frame_{image_id:04d}.jpg",
        width=size,
        height=size,
        K=K,
        viewmat=viewmat,
        rgb_u8=rgb,
        mask_u8=mask,
    )


def test_2dgs_config_enforces_8gb_vram_budgets() -> None:
    """Verify standard and turbo presets enforce 8 GB RTX 4060 VRAM caps and gsplat 1.5.3 packed=False."""
    std = Gaussian2DGSConfig(turbo=False)
    assert std.effective_max_image_size == 960
    assert std.effective_iterations == 7000
    assert std.max_gaussians == 150_000
    assert std.packed is False
    assert std.lambda_mask == 0.5
    assert std.lambda_mask_final == 0.05
    assert std.lambda_normal == 0.05
    assert std.lambda_normal_final == 0.08
    assert std.lambda_dist == 0.01
    assert std.min_opacity == 0.01

    # Verify halfway silhouette decay (0.5 -> 0.05) and final-30% normal ramp (0.05 -> 0.08)
    assert np.isclose(scheduled_lambda_mask(1, std), 0.5)
    assert np.isclose(scheduled_lambda_mask(3500, std), 0.5)
    assert np.isclose(scheduled_lambda_mask(5250, std), 0.275)
    assert np.isclose(scheduled_lambda_mask(7000, std), 0.05)
    assert np.isclose(scheduled_lambda_normal(1000, std), 0.0)
    assert np.isclose(scheduled_lambda_normal(1500, std), 0.05)
    assert np.isclose(scheduled_lambda_normal(4900, std), 0.05)
    assert np.isclose(scheduled_lambda_normal(7000, std), 0.08)
    assert std.min_mask_coverage == 0.02
    assert std.max_mask_coverage == 0.95
    assert std.min_valid_views_for_filter == 20

    turbo = Gaussian2DGSConfig(turbo=True)
    assert turbo.effective_max_image_size == 720
    assert turbo.effective_iterations == 3500
    assert turbo.max_gaussians == 150_000
    assert turbo.packed is False


def test_read_colmap_points3d_bin_roundtrip(tmp_path: Path) -> None:
    """Verify binary COLMAP points3D.bin parser decodes xyz and rgb accurately."""
    pts_path = tmp_path / "points3D.bin"
    with open(pts_path, "wb") as f:
        f.write(struct.pack("<Q", 2))
        # Point 1 with 1 track entry (8 bytes)
        f.write(struct.pack("<Q", 1))
        f.write(struct.pack("<3d", 1.0, 2.0, 3.0))
        f.write(struct.pack("<3B", 255, 128, 0))
        f.write(struct.pack("<d", 0.25))
        f.write(struct.pack("<Q", 1))
        f.write(struct.pack("<II", 1, 42))
        # Point 2 with 0 track entries
        f.write(struct.pack("<Q", 2))
        f.write(struct.pack("<3d", -1.5, 0.5, 4.25))
        f.write(struct.pack("<3B", 10, 20, 30))
        f.write(struct.pack("<d", 0.1))
        f.write(struct.pack("<Q", 0))

    xyz, rgb = read_colmap_points3d_bin(pts_path)
    assert xyz.shape == (2, 3)
    assert rgb.shape == (2, 3)
    assert np.allclose(xyz[0], [1.0, 2.0, 3.0])
    assert np.allclose(xyz[1], [-1.5, 0.5, 4.25])
    assert np.array_equal(rgb[0], [255, 128, 0])
    assert np.array_equal(rgb[1], [10, 20, 30])


def test_filter_sparse_points_by_masks_rejects_background_wall_points() -> None:
    """Verify visual-hull filter (visible_count >= 5 and fg_hits/visible_count >= 0.70)
    rejects background wall points that only occasionally project behind the foreground mask."""
    rng = np.random.default_rng(12)
    # 600 foreground points tightly clustered near origin (projected inside [30..70] in all 10 views)
    fg_pts = rng.uniform(-0.12, 0.12, size=(600, 3))
    # 200 background points offset at x=1.0: pass behind origin in ~2/10 views (< 70%)
    bg_pts = np.column_stack([
        rng.uniform(0.65, 0.85, size=200),
        rng.uniform(-0.10, 0.10, size=200),
        rng.uniform(-0.10, 0.10, size=200),
    ])
    all_pts = np.vstack([fg_pts, bg_pts])
    all_rgb = np.full((len(all_pts), 3), 200, dtype=np.uint8)

    # 10 views orbiting around origin at radius 3.0
    angles = np.linspace(0.0, 2.0 * np.pi, 10, endpoint=False)
    views = [
        _make_view(
            i + 1,
            np.array([3.0 * np.cos(a), 3.0 * np.sin(a), 0.2]),
            mask_box=(36, 36, 64, 64),
        )
        for i, a in enumerate(angles)
    ]

    kept_xyz, kept_rgb, fg_hits = filter_sparse_points_by_masks(
        all_pts,
        all_rgb,
        views,
        min_visible_views=5,
        min_fg_ratio=0.70,
        min_surviving_points=500,
    )

    assert len(kept_xyz) == 600
    assert len(kept_rgb) == 600
    assert np.all(fg_hits[:600] >= 7)
    # Some bg points had >= 2 hits (old filter would have kept them!), but all fail >= 70% visual hull
    assert np.any(fg_hits[600:] >= 2)
    assert np.all(fg_hits[600:] < 7)

    # Verify iterative relaxation (0.70 -> 0.55) when < 500 points survive 0.70
    # Add 10 views where 400 points hit 60% of masks -> should relax to 0.55 and keep them
    relaxed_views = list(views[:6]) + [
        _make_view(
            100 + i,
            np.array([3.0 * np.cos(a), 3.0 * np.sin(a), 0.2]),
            mask_box=(0, 0, 20, 20),  # shifted mask missing origin in 4/10 views (60% fg ratio)
        )
        for i, a in enumerate(angles[6:])
    ]
    kept_relaxed, _, _ = filter_sparse_points_by_masks(
        fg_pts,
        all_rgb[:600],
        relaxed_views,
        min_visible_views=5,
        min_fg_ratio=0.70,
        min_surviving_points=500,
    )
    assert len(kept_relaxed) == 600


def test_compose_debug_panel_produces_triple_width_bgr_image() -> None:
    """Verify 4-panel [GT Masked RGB | Rendered RGB | Median Depth | Normals] convergence render."""
    gt_rgb = np.full((64, 80, 3), 180, dtype=np.uint8)
    gt_mask = np.zeros((64, 80), dtype=np.uint8)
    gt_mask[16:48, 20:60] = 255
    render_rgb = np.full((64, 80, 3), 120, dtype=np.uint8)
    render_depth = np.zeros((64, 80), dtype=np.float32)
    render_depth[16:48, 20:60] = 1.5
    render_normals = np.zeros((64, 80, 3), dtype=np.float32)
    render_normals[16:48, 20:60] = [0.0, 0.0, 1.0]
    render_alpha = np.zeros((64, 80), dtype=np.float32)
    render_alpha[16:48, 20:60] = 1.0

    panel = compose_debug_panel(
        gt_rgb, gt_mask, render_rgb, render_depth,
        render_normals=render_normals, render_alpha=render_alpha,
    )
    assert panel.shape == (64, 320, 3)
    assert panel.dtype == np.uint8
    # Unmasked corner of GT panel should be black
    assert np.all(panel[60, 5] == 0)
    # Depth panel inside object should be colorized (non-zero)
    assert np.any(panel[32, 160 + 40] > 0)
    # Normals panel inside object should be non-zero and outside alpha<0.5 black
    assert np.any(panel[32, 240 + 40] > 0)
    assert np.all(panel[60, 240 + 5] == 0)


def test_composite_2dgs_loss_activates_normal_and_dist_after_step_1500() -> None:
    """Verify CPU PyTorch composite loss contract (Photometric + Mask + post-1500 Normal/Dist)."""
    torch = pytest.importorskip("torch")

    cfg = Gaussian2DGSConfig()
    h, w = 32, 32
    gt_rgb = torch.rand((h, w, 3), dtype=torch.float32)
    gt_mask = torch.ones((h, w, 1), dtype=torch.float32)
    bg = torch.ones((1, 1, 3), dtype=torch.float32)

    render_rgb = (gt_rgb * 0.9).clone().requires_grad_(True)
    render_alphas = torch.full((h, w, 1), 0.8, dtype=torch.float32, requires_grad=True)
    render_normals = torch.tensor([[[0.0, 0.0, 1.0]]], dtype=torch.float32).expand(h, w, 3).clone().requires_grad_(True)
    surf_normals = torch.tensor([[[0.0, 1.0, 0.0]]], dtype=torch.float32).expand(h, w, 3).clone()
    render_distort = torch.full((h, w, 1), 0.01, dtype=torch.float32, requires_grad=True)

    # Step 500 (< 1500): normal and distortion regularization must NOT be applied
    loss_early, metrics_early = compute_2dgs_loss(
        render_rgb=render_rgb,
        render_alphas=render_alphas,
        gt_rgb=gt_rgb,
        gt_mask=gt_mask,
        bg_color=bg,
        step=500,
        config=cfg,
        render_normals=render_normals,
        surf_normals=surf_normals,
        render_distort=render_distort,
    )
    assert metrics_early["normal"] == 0.0
    assert metrics_early["dist"] == 0.0
    assert metrics_early["mask"] > 0.0
    loss_early.backward()
    assert render_rgb.grad is not None
    assert render_alphas.grad is not None

    # Step 2000 (>= 1500): normal consistency and depth distortion MUST activate
    loss_late, metrics_late = compute_2dgs_loss(
        render_rgb=render_rgb.detach().requires_grad_(True),
        render_alphas=render_alphas.detach().requires_grad_(True),
        gt_rgb=gt_rgb,
        gt_mask=gt_mask,
        bg_color=bg,
        step=2000,
        config=cfg,
        render_normals=render_normals.detach().requires_grad_(True),
        surf_normals=surf_normals,
        render_distort=render_distort.detach().requires_grad_(True),
    )
    assert np.isclose(metrics_late["normal"], 1.0, atol=1e-4)  # orthogonal normals -> 1 - 0 = 1.0
    assert np.isclose(metrics_late["dist"], 0.01, atol=1e-5)
    assert metrics_late["total"] > metrics_early["total"]
    loss_late.backward()


def test_load_training_views_excludes_abnormal_masks_with_20_view_fallback(tmp_path: Path) -> None:
    """Verify views with <2% or >95% mask coverage are dropped when >=20 valid views remain,
    and retained via safety fallback when <20 valid views remain."""
    import cv2
    from loom.reconstruction.gaussian_2dgs import Gaussian2DGSReconstructor

    def _build_scene(root: Path, n_good: int, n_empty: int, n_full: int) -> tuple[Path, Path, Path]:
        img_dir = root / "images"
        mask_dir = root / "masks"
        sparse_dir = root / "sparse"
        img_dir.mkdir(parents=True)
        mask_dir.mkdir(parents=True)
        sparse_dir.mkdir(parents=True)

        (sparse_dir / "cameras.txt").write_text("1 PINHOLE 64 64 64.0 64.0 32.0 32.0\n", encoding="utf-8")
        (sparse_dir / "points3D.txt").write_text("1 0.0 0.0 2.0 200 200 200 0.1\n", encoding="utf-8")

        img_lines: list[str] = []
        total = n_good + n_empty + n_full
        for idx in range(1, total + 1):
            name = f"frame_{idx:04d}.jpg"
            cv2.imwrite(str(img_dir / name), np.full((64, 64, 3), 120, dtype=np.uint8))
            mask = np.zeros((64, 64), dtype=np.uint8)
            if idx <= n_good:
                mask[16:48, 16:48] = 255  # 25% coverage (valid)
            elif idx <= n_good + n_empty:
                pass  # 0% coverage (corrupted/empty)
            else:
                mask[:, :] = 255  # 100% coverage (overfull)
            cv2.imwrite(str(mask_dir / f"frame_{idx:04d}.png"), mask)
            img_lines.append(f"{idx} 1 0 0 0 0 0 0 1 {name}\n\n")
        (sparse_dir / "images.txt").write_text("".join(img_lines), encoding="utf-8")
        return img_dir, mask_dir, sparse_dir

    reconstructor = Gaussian2DGSReconstructor(Gaussian2DGSConfig())

    # Case 1: 22 good + 3 empty + 2 full -> >=20 valid remain -> excludes the 5 bad views
    i1, m1, s1 = _build_scene(tmp_path / "case_filter", n_good=22, n_empty=3, n_full=2)
    views1, _, _ = reconstructor.load_training_views(i1, m1, s1)
    assert len(views1) == 22

    # Case 2: 10 good + 3 empty -> <20 valid remain -> safety fallback retains all 13 views
    i2, m2, s2 = _build_scene(tmp_path / "case_fallback", n_good=10, n_empty=3, n_full=0)
    views2, _, _ = reconstructor.load_training_views(i2, m2, s2)
    assert len(views2) == 13

    # All-pose TSDF loader must retain ALL 27 registered poses in case_filter while assigning
    # mask_u8=None to excluded views so TSDF relies solely on 3D-consistent render_alpha.
    valid_names = [v.name for v in views1]
    all_poses = reconstructor.load_all_registered_poses(i1, m1, s1, valid_view_names=valid_names)
    assert len(all_poses) == 27
    excluded_poses = [p for p in all_poses if p.name not in set(valid_names)]
    valid_poses = [p for p in all_poses if p.name in set(valid_names)]
    assert len(excluded_poses) == 5
    assert len(valid_poses) == 22
    assert all(p.mask_u8 is None for p in excluded_poses)
    assert all(p.mask_u8 is not None for p in valid_poses)


def test_gsplat_153_cuda_shape_smoke() -> None:
    """Real CUDA smoke test verifying gsplat 1.5.3 rasterization_2dgs tensor shapes and backward."""
    torch = pytest.importorskip("torch")
    if not torch.cuda.is_available():
        pytest.skip("CUDA GPU unavailable")
    gsplat = pytest.importorskip("gsplat")

    # Skip cleanly inside restricted sandboxes where nvcc/CUDA toolkit is not mounted
    try:
        from gsplat.cuda import _backend
        if getattr(_backend, "_C", None) is None:
            pytest.skip("gsplat CUDA extension unavailable in restricted sandbox")
    except Exception:
        pytest.skip("gsplat CUDA extension unavailable")

    cfg = Gaussian2DGSConfig()
    device = torch.device("cuda")
    n = 100
    means = torch.randn((n, 3), device=device, requires_grad=True)
    quats = torch.tensor([[1.0, 0.0, 0.0, 0.0]], device=device).expand(n, 4).clone().requires_grad_(True)
    scales = torch.full((n, 3), 0.05, device=device, requires_grad=True)
    opacities = torch.full((n,), 0.8, device=device, requires_grad=True)
    colors = torch.zeros((n, 9, 3), device=device, requires_grad=True)
    viewmat = torch.eye(4, device=device).unsqueeze(0)
    viewmat[0, 2, 3] = 3.0
    K = torch.tensor([[[100.0, 0.0, 64.0], [0.0, 100.0, 64.0], [0.0, 0.0, 1.0]]], device=device)

    rc, ra, rn, sn, rd, rm, info = gsplat.rasterization_2dgs(
        means=means,
        quats=quats,
        scales=scales,
        opacities=opacities,
        colors=colors,
        viewmats=viewmat,
        Ks=K,
        width=64,
        height=64,
        sh_degree=2,
        render_mode="RGB+ED",
        distloss=True,
        packed=cfg.packed,
    )
    assert rc.shape == (1, 64, 64, 4)
    assert ra.shape == (1, 64, 64, 1)
    assert rm.shape == (1, 64, 64, 1)
    info["gradient_2dgs"].retain_grad()
    loss, _ = compute_2dgs_loss(
        render_rgb=rc[0, ..., :3],
        render_alphas=ra[0],
        gt_rgb=torch.rand((64, 64, 3), device=device),
        gt_mask=torch.ones((64, 64), device=device),
        bg_color=torch.full((1, 1, 3), 0.5, device=device),
        step=1600,
        config=cfg,
        render_normals=rn[0] if rn.ndim == 4 else rn,
        surf_normals=sn[0] if sn.ndim == 4 else sn,
        render_distort=rd[0] if rd.ndim == 4 else rd,
    )
    loss.backward()
    assert means.grad is not None
    assert info["gradient_2dgs"].grad is not None
    assert float(info["gradient_2dgs"].grad.abs().sum().item()) > 0.0



