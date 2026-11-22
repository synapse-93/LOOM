"""Masked 2D Gaussian Splatting (2DGS) surface reconstructor engineered for gsplat 1.5.3."""

from __future__ import annotations

import logging
import math
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

import cv2
import numpy as np

from loom.reconstruction.visual_hull import read_colored_ply
from loom.scaling.aruco import ColmapCamera, ColmapImage, load_colmap_model

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Gaussian2DGSConfig:
    """Hyperparameters and 8 GB RTX 4060 VRAM budgets for Masked 2DGS optimization."""

    iterations: int = 7000
    turbo: bool = False
    max_image_size: int = 960
    turbo_max_image_size: int = 720
    turbo_iterations: int = 3500
    max_gaussians: int = 150_000
    sh_degree: int = 2
    # Note: gsplat==1.5.3 rasterization_2dgs has an upstream packed=True SH/depth indexing bug
    # (broadcasts shs to [1, N, K, 3] without packing by gaussian_ids). Using packed=False on
    # single-view C=1 steps uses ~6 MB for 150k surfels and stays well below the 6.5 GB VRAM cap.
    packed: bool = False
    min_visible_views: int = 5
    min_fg_ratio: float = 0.70
    min_surviving_points: int = 500
    min_mask_coverage: float = 0.02
    max_mask_coverage: float = 0.95
    min_valid_views_for_filter: int = 20

    # Loss weights
    # Note: gsplat 1.5.3 render_distort is L1 world-space distortion (unlike L2 NDC in Inria 2DGS),
    # so lambda_dist=0.01 prevents the 100x loss explosion that collapses surfel opacities.
    lambda_ssim: float = 0.2
    lambda_mask: float = 0.5
    lambda_mask_final: float = 0.05
    lambda_normal: float = 0.05
    lambda_normal_final: float = 0.08
    lambda_dist: float = 0.01
    regularization_start_step: int = 1500

    # Adaptive densification & pruning
    densify_from_iter: int = 500
    densify_interval: int = 250
    opacity_reset_interval: int = 3000
    min_opacity: float = 0.02
    grad_threshold: float = 0.0002
    max_scale_ratio: float = 0.15

    # Learning rates
    lr_means: float = 1.6e-4
    lr_means_final: float = 1.6e-6
    lr_scales: float = 5e-3
    lr_quats: float = 1e-3
    lr_opacities: float = 5e-2
    lr_sh0: float = 2.5e-3
    lr_sh_rest: float = 1.25e-4

    log_interval: int = 500

    @property
    def effective_iterations(self) -> int:
        return self.turbo_iterations if self.turbo else self.iterations

    @property
    def effective_max_image_size(self) -> int:
        return min(self.max_image_size, self.turbo_max_image_size) if self.turbo else self.max_image_size

    @property
    def effective_densify_until(self) -> int:
        return int(round(self.effective_iterations * 0.65))


@dataclass
class TrainingView:
    """Single undistorted camera view with resized RGB image, binary mask, and intrinsics."""

    image_id: int
    name: str
    width: int
    height: int
    K: np.ndarray          # (3, 3) float64
    viewmat: np.ndarray    # (4, 4) float64 world-to-camera [R | t]
    rgb_u8: np.ndarray     # (H, W, 3) uint8 RGB (stored on CPU to save VRAM)
    mask_u8: np.ndarray    # (H, W) uint8 binary {0, 255}


@dataclass
class Trained2DGSModel:
    """Container holding optimized 2DGS surfel parameters and metadata for TSDF extraction."""

    means: Any            # torch.Tensor (N, 3)
    scales: Any           # torch.Tensor (N, 3) log-scales
    quats: Any            # torch.Tensor (N, 4)
    opacities: Any        # torch.Tensor (N,) logits
    sh0: Any              # torch.Tensor (N, 1, 3)
    sh_rest: Any          # torch.Tensor (N, K-1, 3)
    sh_degree: int
    views: list[TrainingView]
    final_loss: float
    num_surfels: int
    scene_radius: float
    object_center: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float64))
    object_radius: float = 0.5
    init_surfels: int = 0
    iterations: int = 0
    peak_vram_mib: float = 0.0
    debug_render_paths: list[str] = field(default_factory=list)

    @property
    def means_np(self) -> np.ndarray:
        return self.means.detach().cpu().numpy().astype(np.float64)

    @property
    def opacities_np(self) -> np.ndarray:
        import torch

        return torch.sigmoid(self.opacities.detach()).cpu().numpy().astype(np.float64)

    def high_opacity_means_np(self, min_opacity: float = 0.35) -> np.ndarray:
        """Return 3D coordinates of trained surfels with sigmoid(opacity) > min_opacity."""
        pts = self.means_np
        ops = self.opacities_np
        valid = ops > float(min_opacity)
        if int(np.count_nonzero(valid)) >= 16:
            return pts[valid]
        return pts

    def to_manifest_dict(self) -> dict[str, Any]:
        return {
            "iterations": int(self.iterations),
            "init_surfels": int(self.init_surfels),
            "final_surfels": int(self.num_surfels),
            "final_loss": round(float(self.final_loss), 6),
            "peak_vram_mib": round(float(self.peak_vram_mib), 1),
            "debug_render_paths": list(self.debug_render_paths),
            "valid_views_used": len(self.views),
        }


# -----------------------------------------------------------------------------
# COLMAP Sparse Point Cloud I/O & Fallback Mask Filtering
# -----------------------------------------------------------------------------


def read_colmap_points3d_bin(path: Path | str) -> tuple[np.ndarray, np.ndarray]:
    """Parse COLMAP ``points3D.bin`` returning ``(xyz (N, 3) float64, rgb (N, 3) uint8)``."""
    p = Path(path).resolve()
    xyz_list: list[tuple[float, float, float]] = []
    rgb_list: list[tuple[int, int, int]] = []
    with open(p, "rb") as f:
        num_points = struct.unpack("<Q", f.read(8))[0]
        for _ in range(num_points):
            _point_id = struct.unpack("<Q", f.read(8))[0]
            x, y, z = struct.unpack("<3d", f.read(24))
            r, g, b = struct.unpack("<3B", f.read(3))
            _error = struct.unpack("<d", f.read(8))[0]
            track_len = struct.unpack("<Q", f.read(8))[0]
            if track_len > 0:
                f.seek(track_len * 8, 1)
            xyz_list.append((x, y, z))
            rgb_list.append((r, g, b))

    if not xyz_list:
        return np.zeros((0, 3), dtype=np.float64), np.zeros((0, 3), dtype=np.uint8)
    return np.asarray(xyz_list, dtype=np.float64), np.asarray(rgb_list, dtype=np.uint8)


def read_colmap_points3d_txt(path: Path | str) -> tuple[np.ndarray, np.ndarray]:
    """Parse COLMAP ``points3D.txt`` returning ``(xyz (N, 3) float64, rgb (N, 3) uint8)``."""
    p = Path(path).resolve()
    xyz_list: list[tuple[float, float, float]] = []
    rgb_list: list[tuple[int, int, int]] = []
    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            if len(parts) >= 7:
                xyz_list.append((float(parts[1]), float(parts[2]), float(parts[3])))
                rgb_list.append((int(parts[4]), int(parts[5]), int(parts[6])))

    if not xyz_list:
        return np.zeros((0, 3), dtype=np.float64), np.zeros((0, 3), dtype=np.uint8)
    return np.asarray(xyz_list, dtype=np.float64), np.asarray(rgb_list, dtype=np.uint8)


def load_colmap_points3d(sparse_dir: Path | str) -> tuple[np.ndarray, np.ndarray]:
    """Load COLMAP sparse 3D points from ``points3D.bin`` or ``points3D.txt``."""
    d = Path(sparse_dir).resolve()
    if (d / "0" / "points3D.bin").is_file():
        return read_colmap_points3d_bin(d / "0" / "points3D.bin")
    if (d / "points3D.bin").is_file():
        return read_colmap_points3d_bin(d / "points3D.bin")
    if (d / "0" / "points3D.txt").is_file():
        return read_colmap_points3d_txt(d / "0" / "points3D.txt")
    if (d / "points3D.txt").is_file():
        return read_colmap_points3d_txt(d / "points3D.txt")
    raise FileNotFoundError(f"No points3D.bin or points3D.txt found in {d}")


def filter_sparse_points_by_masks(
    points_xyz: np.ndarray,
    points_rgb: np.ndarray,
    views: Sequence[TrainingView],
    *,
    min_visible_views: int = 5,
    min_fg_ratio: float = 0.70,
    min_surviving_points: int = 500,
    relax_ratios: tuple[float, ...] = (0.55, 0.40),
    min_mask_coverage: float = 0.02,
    max_mask_coverage: float = 0.95,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Fallback visual-hull filter on sparse COLMAP 3D points when visual_hull_points.ply is absent."""
    pts = np.asarray(points_xyz, dtype=np.float64)
    rgb = np.asarray(points_rgb, dtype=np.uint8)
    n_pts = len(pts)
    if n_pts == 0:
        return pts, rgb, np.zeros(0, dtype=np.int32)

    valid_views = [
        v
        for v in views
        if min_mask_coverage
        <= (float(np.count_nonzero(v.mask_u8)) / float(max(v.mask_u8.size, 1)))
        <= max_mask_coverage
    ]
    active_views = valid_views if valid_views else list(views)
    if not active_views:
        return pts, rgb, np.zeros(n_pts, dtype=np.int32)

    visible_count = np.zeros(n_pts, dtype=np.int32)
    fg_hits = np.zeros(n_pts, dtype=np.int32)

    for view in active_views:
        R = view.viewmat[:3, :3]
        t = view.viewmat[:3, 3]
        K = view.K
        mask = view.mask_u8

        cam_pts = (pts @ R.T) + t[None, :]
        z = cam_pts[:, 2]
        front = z > 1e-4
        if not np.any(front):
            continue

        idx_front = np.nonzero(front)[0]
        x_f = cam_pts[idx_front, 0] / z[idx_front]
        y_f = cam_pts[idx_front, 1] / z[idx_front]

        u = np.rint(K[0, 0] * x_f + K[0, 2]).astype(np.int64)
        v = np.rint(K[1, 1] * y_f + K[1, 2]).astype(np.int64)

        in_bounds = (u >= 0) & (u < view.width) & (v >= 0) & (v < view.height)
        if not np.any(in_bounds):
            continue

        idx_in = idx_front[in_bounds]
        visible_count[idx_in] += 1
        fg_hit = mask[v[in_bounds], u[in_bounds]] > 0
        if np.any(fg_hit):
            fg_hits[idx_in[fg_hit]] += 1

    eff_min_vis = min(int(min_visible_views), len(active_views))
    ratio = np.where(visible_count > 0, fg_hits.astype(np.float64) / np.maximum(visible_count, 1), 0.0)

    thresholds = [float(min_fg_ratio), *[float(r) for r in relax_ratios if float(r) < float(min_fg_ratio)]]
    keep = np.zeros(n_pts, dtype=bool)
    for thresh in thresholds:
        cand = (visible_count >= eff_min_vis) & (ratio >= thresh)
        keep = cand
        if int(np.count_nonzero(cand)) >= int(min_surviving_points):
            break

    if int(np.count_nonzero(keep)) == 0:
        keep = fg_hits >= 1
        if int(np.count_nonzero(keep)) == 0:
            return pts, rgb, fg_hits

    return pts[keep], rgb[keep], fg_hits


def compose_debug_panel(
    gt_rgb: np.ndarray,
    gt_mask: np.ndarray,
    render_rgb: np.ndarray,
    render_depth: np.ndarray,
    render_normals: Optional[np.ndarray] = None,
    render_alpha: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Create a horizontal 4-panel (or 3-panel) BGR convergence audit image.

    Panels: [GT Masked RGB | Rendered RGB | Colorized Median Depth | Rendered Normals]
    """
    h, w = gt_rgb.shape[:2]
    mask_bool = np.asarray(gt_mask) > 127
    if mask_bool.ndim == 3:
        mask_bool = mask_bool[:, :, 0]

    gt_masked = np.where(mask_bool[:, :, None], np.asarray(gt_rgb, dtype=np.uint8), np.uint8(0))
    gt_bgr = cv2.cvtColor(gt_masked, cv2.COLOR_RGB2BGR)

    ren_u8 = np.asarray(render_rgb, dtype=np.uint8)
    if ren_u8.shape[:2] != (h, w):
        ren_u8 = cv2.resize(ren_u8, (w, h), interpolation=cv2.INTER_AREA)
    ren_bgr = cv2.cvtColor(ren_u8, cv2.COLOR_RGB2BGR)

    depth = np.asarray(render_depth, dtype=np.float32)
    if depth.ndim == 3:
        depth = depth[:, :, 0]
    if depth.shape[:2] != (h, w):
        depth = cv2.resize(depth, (w, h), interpolation=cv2.INTER_NEAREST)

    depth_vis = np.zeros((h, w, 3), dtype=np.uint8)
    valid = np.isfinite(depth) & (depth > 0.0)
    if render_alpha is not None:
        a = np.asarray(render_alpha, dtype=np.float32)
        if a.ndim == 3:
            a = a[:, :, 0]
        valid &= a >= 0.5
    if np.any(valid):
        vals = depth[valid]
        d_lo = float(np.percentile(vals, 2.0))
        d_hi = float(np.percentile(vals, 98.0))
        span = max(d_hi - d_lo, 1e-5)
        norm = np.clip((depth - d_lo) / span, 0.0, 1.0)
        colored = cv2.applyColorMap((norm * 255.0).astype(np.uint8), cv2.COLORMAP_TURBO)
        depth_vis[valid] = colored[valid]

    panels = [gt_bgr, ren_bgr, depth_vis]
    labels = ["GT Masked RGB", "2DGS Rendered RGB", "2DGS Median Depth"]

    if render_normals is not None:
        norms = np.asarray(render_normals, dtype=np.float32)
        if norms.shape[:2] != (h, w):
            norms = cv2.resize(norms, (w, h), interpolation=cv2.INTER_LINEAR)
        n_len = np.linalg.norm(norms, axis=-1, keepdims=True)
        norms_unit = norms / np.maximum(n_len, 1e-6)
        norms_rgb = np.clip((norms_unit * 0.5 + 0.5) * 255.0, 0.0, 255.0).astype(np.uint8)
        norms_bgr = cv2.cvtColor(norms_rgb, cv2.COLOR_RGB2BGR)
        if render_alpha is not None:
            a = np.asarray(render_alpha, dtype=np.float32)
            if a.ndim == 3:
                a = a[:, :, 0]
            norms_bgr[a < 0.5] = 0
        panels.append(norms_bgr)
        labels.append("2DGS Normals")

    for panel, text in zip(panels, labels):
        cv2.rectangle(panel, (0, 0), (w, 28), (16, 18, 22), -1)
        cv2.putText(
            panel,
            text,
            (8, 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (236, 238, 242),
            1,
            cv2.LINE_AA,
        )

    return np.hstack(panels)


# -----------------------------------------------------------------------------
# Differentiable SSIM & Composite 2DGS Loss
# -----------------------------------------------------------------------------


def _gaussian_window_2d(window_size: int, sigma: float, channels: int, device: Any, dtype: Any) -> Any:
    import torch

    coords = torch.arange(window_size, device=device, dtype=dtype) - (window_size // 2)
    g1d = torch.exp(-(coords**2) / (2.0 * sigma * sigma))
    g1d = g1d / g1d.sum()
    g2d = torch.outer(g1d, g1d)
    return g2d.view(1, 1, window_size, window_size).expand(channels, 1, window_size, window_size).contiguous()


def compute_ssim(img1: Any, img2: Any, window_size: int = 11, sigma: float = 1.5) -> Any:
    """Compute differentiable scalar SSIM between two (H, W, C) tensors in [0, 1]."""
    import torch.nn.functional as F

    x = img1.permute(2, 0, 1).unsqueeze(0)
    y = img2.permute(2, 0, 1).unsqueeze(0)
    channels = x.shape[1]
    window = _gaussian_window_2d(window_size, sigma, channels, x.device, x.dtype)
    pad = window_size // 2

    mu1 = F.conv2d(x, window, padding=pad, groups=channels)
    mu2 = F.conv2d(y, window, padding=pad, groups=channels)
    mu1_sq = mu1 * mu1
    mu2_sq = mu2 * mu2
    mu1_mu2 = mu1 * mu2

    sigma1_sq = F.conv2d(x * x, window, padding=pad, groups=channels) - mu1_sq
    sigma2_sq = F.conv2d(y * y, window, padding=pad, groups=channels) - mu2_sq
    sigma12 = F.conv2d(x * y, window, padding=pad, groups=channels) - mu1_mu2

    c1 = 0.01**2
    c2 = 0.03**2
    ssim_map = ((2.0 * mu1_mu2 + c1) * (2.0 * sigma12 + c2)) / (
        (mu1_sq + mu2_sq + c1) * (sigma1_sq + sigma2_sq + c2)
    )
    return ssim_map.mean()


def scheduled_lambda_mask(step: int, config: Gaussian2DGSConfig) -> float:
    """Keep lambda_mask steady for the first 50% of training, then linearly decay to lambda_mask_final.

    This locks the silhouette and removes room floaters early while letting multi-view RGB and
    normal consistency heal per-frame 2D mask dropouts during the second half of optimization.
    """
    total = max(int(config.effective_iterations), 1)
    half = int(0.5 * total)
    if step <= half:
        return float(config.lambda_mask)
    span = max(total - half, 1)
    t = min(max(float(step - half) / float(span), 0.0), 1.0)
    return float(config.lambda_mask + t * (config.lambda_mask_final - config.lambda_mask))


def scheduled_lambda_normal(step: int, config: Gaussian2DGSConfig) -> float:
    """Return normal consistency weight, ramping gently from lambda_normal to lambda_normal_final in final 30%."""
    if step < int(config.regularization_start_step):
        return 0.0
    total = max(int(config.effective_iterations), 1)
    ramp_start = int(0.7 * total)
    if step <= ramp_start:
        return float(config.lambda_normal)
    span = max(total - ramp_start, 1)
    t = min(max(float(step - ramp_start) / float(span), 0.0), 1.0)
    return float(config.lambda_normal + t * (config.lambda_normal_final - config.lambda_normal))


def compute_2dgs_loss(
    render_rgb: Any,
    render_alphas: Any,
    gt_rgb: Any,
    gt_mask: Any,
    bg_color: Any,
    *,
    step: int,
    config: Gaussian2DGSConfig,
    render_normals: Optional[Any] = None,
    surf_normals: Optional[Any] = None,
    render_distort: Optional[Any] = None,
) -> tuple[Any, dict[str, float]]:
    """Compute composite Masked 2DGS loss: Photometric + Scheduled Silhouette + Normal + Distortion."""
    import torch.nn.functional as F

    alpha_3 = render_alphas if render_alphas.ndim == 3 else render_alphas.unsqueeze(-1)
    mask_3 = gt_mask if gt_mask.ndim == 3 else gt_mask.unsqueeze(-1)

    comp_rgb = render_rgb + (1.0 - alpha_3) * bg_color
    gt_comp = gt_rgb * mask_3 + (1.0 - mask_3) * bg_color

    l1_loss = F.l1_loss(comp_rgb, gt_comp)
    ssim_val = compute_ssim(comp_rgb, gt_comp)
    photo_loss = (1.0 - config.lambda_ssim) * l1_loss + config.lambda_ssim * (1.0 - ssim_val)

    w_mask = scheduled_lambda_mask(step, config)
    mask_loss = F.l1_loss(alpha_3, mask_3)
    total_loss = photo_loss + w_mask * mask_loss

    normal_loss_val = 0.0
    dist_loss_val = 0.0
    w_normal = scheduled_lambda_normal(step, config)

    if step >= config.regularization_start_step:
        if render_normals is not None and surf_normals is not None:
            rn = F.normalize(render_normals, dim=-1, eps=1e-6)
            sn = F.normalize(surf_normals, dim=-1, eps=1e-6)
            cos_sim = (rn * sn).sum(dim=-1)
            mask_2d = mask_3[..., 0]
            normal_loss = ((1.0 - cos_sim) * mask_2d).mean()
            total_loss = total_loss + w_normal * normal_loss
            normal_loss_val = float(normal_loss.detach().item())

        if render_distort is not None:
            dist_2d = render_distort[..., 0] if render_distort.ndim == 3 else render_distort
            dist_loss = (dist_2d * mask_3[..., 0]).mean()
            total_loss = total_loss + config.lambda_dist * dist_loss
            dist_loss_val = float(dist_loss.detach().item())

    metrics = {
        "total": float(total_loss.detach().item()),
        "photo": float(photo_loss.detach().item()),
        "mask": float(mask_loss.detach().item()),
        "normal": normal_loss_val,
        "dist": dist_loss_val,
        "lambda_mask": w_mask,
        "lambda_normal": w_normal,
    }
    return total_loss, metrics


# -----------------------------------------------------------------------------
# Masked 2DGS Reconstructor
# -----------------------------------------------------------------------------


class Gaussian2DGSReconstructor:
    """Optimizes a foreground-masked 2D Gaussian Splatting model from manifest-validated views."""

    def __init__(self, config: Optional[Gaussian2DGSConfig] = None) -> None:
        self.config = config or Gaussian2DGSConfig()

    def load_training_views(
        self,
        images_dir: Path | str,
        masks_dir: Path | str,
        sparse_dir: Path | str,
        *,
        valid_view_names: Optional[Sequence[str]] = None,
        init_ply_path: Optional[Path | str] = None,
    ) -> tuple[list[TrainingView], np.ndarray, np.ndarray]:
        """Load undistorted PINHOLE views restricted to valid_views and visual-hull seed points."""
        img_root = Path(images_dir).resolve()
        mask_root = Path(masks_dir).resolve()
        sparse_root = Path(sparse_dir).resolve()

        cameras, images = load_colmap_model(sparse_root)
        if not images:
            raise RuntimeError(f"No registered images found in undistorted COLMAP model: {sparse_root}")

        allowed_set = set(valid_view_names) if valid_view_names is not None else None
        max_dim = self.config.effective_max_image_size
        views: list[TrainingView] = []

        for img_id in sorted(images.keys()):
            col_img: ColmapImage = images[img_id]
            if allowed_set is not None and col_img.name not in allowed_set:
                continue

            cam: Optional[ColmapCamera] = cameras.get(col_img.camera_id)
            if cam is None:
                continue

            img_path = img_root / col_img.name
            if not img_path.is_file():
                continue

            mask_path = mask_root / f"{Path(col_img.name).stem}.png"
            if not mask_path.is_file():
                continue

            bgr = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
            mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
            if bgr is None or mask is None:
                continue

            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]
            K = cam.K.copy()

            if cam.width > 0 and cam.height > 0 and (w != cam.width or h != cam.height):
                K[0, 0] *= w / float(cam.width)
                K[0, 2] *= w / float(cam.width)
                K[1, 1] *= h / float(cam.height)
                K[1, 2] *= h / float(cam.height)

            if mask.shape[:2] != (h, w):
                mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)

            long_edge = max(h, w)
            if long_edge > max_dim:
                scale = float(max_dim) / float(long_edge)
                new_w = max(16, int(round(w * scale)))
                new_h = max(16, int(round(h * scale)))
                rgb = cv2.resize(rgb, (new_w, new_h), interpolation=cv2.INTER_AREA)
                mask = cv2.resize(mask, (new_w, new_h), interpolation=cv2.INTER_NEAREST)
                K[0, 0] *= new_w / float(w)
                K[0, 2] *= new_w / float(w)
                K[1, 1] *= new_h / float(h)
                K[1, 2] *= new_h / float(h)
                w, h = new_w, new_h

            mask_bin = np.where(mask >= 128, np.uint8(255), np.uint8(0))

            viewmat = np.eye(4, dtype=np.float64)
            viewmat[:3, :3] = col_img.R
            viewmat[:3, 3] = col_img.tvec

            views.append(
                TrainingView(
                    image_id=img_id,
                    name=col_img.name,
                    width=w,
                    height=h,
                    K=K,
                    viewmat=viewmat,
                    rgb_u8=rgb,
                    mask_u8=mask_bin,
                )
            )

        if not views:
            raise RuntimeError("No valid (image, mask, pose) training views could be loaded for 2DGS.")

        # Apply coverage guard when explicit manifest valid_view_names was not supplied
        if allowed_set is None:
            total_loaded = len(views)
            valid_views = [
                v
                for v in views
                if self.config.min_mask_coverage
                <= (float(np.count_nonzero(v.mask_u8)) / float(v.mask_u8.size))
                <= self.config.max_mask_coverage
            ]
            excluded_count = total_loaded - len(valid_views)
            if excluded_count > 0:
                if len(valid_views) >= self.config.min_valid_views_for_filter:
                    logger.info(
                        "[2DGS] Excluded %d/%d views with abnormal mask coverage; retaining %d valid views.",
                        excluded_count,
                        total_loaded,
                        len(valid_views),
                    )
                    views = valid_views
                else:
                    logger.warning(
                        "[2DGS] %d/%d views abnormal, but only %d valid remain (< %d fallback); retaining all.",
                        excluded_count,
                        total_loaded,
                        len(valid_views),
                        self.config.min_valid_views_for_filter,
                    )

        # Prefer visual_hull_points.ply strictly when provided
        if init_ply_path is not None and Path(init_ply_path).is_file():
            fg_xyz, fg_rgb = read_colored_ply(init_ply_path)
            logger.info(
                "[2DGS] Loaded %d manifest-validated views (max_dim=%d) and %d visual-hull seed surfels from %s",
                len(views),
                max_dim,
                len(fg_xyz),
                init_ply_path,
            )
            return views, fg_xyz, fg_rgb

        raw_xyz, raw_rgb = load_colmap_points3d(sparse_root)
        fg_xyz, fg_rgb, _ = filter_sparse_points_by_masks(
            raw_xyz,
            raw_rgb,
            views,
            min_visible_views=self.config.min_visible_views,
            min_fg_ratio=self.config.min_fg_ratio,
            min_surviving_points=self.config.min_surviving_points,
            min_mask_coverage=self.config.min_mask_coverage,
            max_mask_coverage=self.config.max_mask_coverage,
        )
        logger.info(
            "[2DGS] Loaded %d views (max_dim=%d) and filtered sparse points: %d -> %d foreground points",
            len(views),
            max_dim,
            len(raw_xyz),
            len(fg_xyz),
        )
        return views, fg_xyz, fg_rgb

    @staticmethod
    def _estimate_initial_scales(points: np.ndarray, object_radius: float) -> np.ndarray:
        """Initialize thin 2D surfel log-scales from 3-NN spacing clamped relative to object_radius."""
        from scipy.spatial import cKDTree

        n = len(points)
        max_init_scale = max(0.08 * float(object_radius), 1e-3)
        if n < 4:
            log_s = math.log(min(0.01 * float(object_radius), max_init_scale))
            return np.full((n, 3), log_s, dtype=np.float32)

        tree = cKDTree(points)
        dists, _ = tree.query(points, k=min(4, n))
        mean_dist = np.mean(dists[:, 1:], axis=1)
        mean_dist = np.clip(mean_dist, 1e-4, max_init_scale)
        log_s = np.log(mean_dist).astype(np.float32)
        # Thin 2D disk surfels: tangent (sx, sy) from 3-NN, normal-axis sz significantly thinner
        return np.column_stack([log_s, log_s, log_s - 2.5]).astype(np.float32)

    def train(
        self,
        images_dir: Path | str,
        masks_dir: Path | str,
        sparse_dir: Path | str,
        *,
        valid_view_names: Optional[Sequence[str]] = None,
        init_ply_path: Optional[Path | str] = None,
        object_center: Optional[Sequence[float]] = None,
        object_radius: Optional[float] = None,
        debug_dir: Optional[Path | str] = None,
    ) -> Trained2DGSModel:
        """Train Masked 2DGS surfels on CUDA GPU within the 8 GB RTX 4060 VRAM budget."""
        import torch
        import torch.nn.functional as F
        from gsplat import rasterization_2dgs

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA GPU is required for 2D Gaussian Splatting training.")

        device = torch.device("cuda")
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(device)

        views, init_xyz, init_rgb = self.load_training_views(
            images_dir,
            masks_dir,
            sparse_dir,
            valid_view_names=valid_view_names,
            init_ply_path=init_ply_path,
        )

        if len(init_xyz) > self.config.max_gaussians:
            rng_cap = np.random.default_rng(42)
            keep_idx = rng_cap.choice(len(init_xyz), size=self.config.max_gaussians, replace=False)
            init_xyz = init_xyz[keep_idx]
            init_rgb = init_rgb[keep_idx]

        # Strictly lock object_center & object_radius to tight foreground core (never room orbit)
        if object_center is not None and len(object_center) == 3:
            obj_center = np.asarray(object_center, dtype=np.float64)
        else:
            obj_center = np.median(init_xyz, axis=0)

        if object_radius is not None and float(object_radius) > 0:
            obj_radius = max(float(object_radius), 0.05)
        else:
            dists = np.linalg.norm(init_xyz - obj_center[None, :], axis=1)
            obj_radius = max(float(np.percentile(dists, 95.0)) if len(dists) > 0 else 0.5, 0.05)

        n_init = len(init_xyz)
        init_scales = self._estimate_initial_scales(init_xyz, obj_radius)

        means = torch.nn.Parameter(torch.tensor(init_xyz, dtype=torch.float32, device=device))
        scales = torch.nn.Parameter(torch.tensor(init_scales, dtype=torch.float32, device=device))
        quats_init = torch.zeros((n_init, 4), dtype=torch.float32, device=device)
        quats_init[:, 0] = 1.0
        quats = torch.nn.Parameter(quats_init)
        opacities = torch.nn.Parameter(
            torch.logit(torch.full((n_init,), 0.5, dtype=torch.float32, device=device))
        )

        c0 = 0.28209479177387814
        rgb_float = torch.tensor(init_rgb, dtype=torch.float32, device=device) / 255.0
        sh0 = torch.nn.Parameter(((rgb_float - 0.5) / c0).unsqueeze(1).contiguous())
        num_sh_bases = (self.config.sh_degree + 1) ** 2
        sh_rest = torch.nn.Parameter(
            torch.zeros((n_init, max(0, num_sh_bases - 1), 3), dtype=torch.float32, device=device)
        )

        params = {
            "means": means,
            "scales": scales,
            "quats": quats,
            "opacities": opacities,
            "sh0": sh0,
            "sh_rest": sh_rest,
        }

        def _means_lr_at(step_idx: int) -> float:
            t = min(max(float(step_idx) / float(max(total_iters, 1)), 0.0), 1.0)
            lr_init = self.config.lr_means * obj_radius
            lr_fin = self.config.lr_means_final * obj_radius
            return float(math.exp(math.log(max(lr_init, 1e-12)) * (1.0 - t) + math.log(max(lr_fin, 1e-12)) * t))

        def _make_optimizer(p: dict[str, torch.nn.Parameter], step_idx: int = 0) -> torch.optim.Adam:
            return torch.optim.Adam(
                [
                    {"params": [p["means"]], "lr": _means_lr_at(step_idx), "name": "means"},
                    {"params": [p["scales"]], "lr": self.config.lr_scales, "name": "scales"},
                    {"params": [p["quats"]], "lr": self.config.lr_quats, "name": "quats"},
                    {"params": [p["opacities"]], "lr": self.config.lr_opacities, "name": "opacities"},
                    {"params": [p["sh0"]], "lr": self.config.lr_sh0, "name": "sh0"},
                    {"params": [p["sh_rest"]], "lr": self.config.lr_sh_rest, "name": "sh_rest"},
                ],
                eps=1e-15,
            )

        total_iters = self.config.effective_iterations
        densify_until = self.config.effective_densify_until
        optimizer = _make_optimizer(params, step_idx=0)
        grad_accum = torch.zeros(n_init, dtype=torch.float32, device=device)
        grad_denom = torch.zeros(n_init, dtype=torch.float32, device=device)
        last_opacity_reset = -10_000

        rng = np.random.default_rng(42)
        bg_palette = (0.0, 0.5, 1.0)  # black / mid-gray / white per-step BG randomization
        last_loss = 0.0

        logger.info(
            "[2DGS] Starting Masked 2DGS optimization: iterations=%d, init_surfels=%d, max_gaussians=%d, "
            "valid_views=%d, object_radius=%.4f, lr_means=%.6f",
            total_iters,
            n_init,
            self.config.max_gaussians,
            len(views),
            obj_radius,
            self.config.lr_means * obj_radius,
        )

        for step in range(1, total_iters + 1):
            optimizer.param_groups[0]["lr"] = _means_lr_at(step)
            view = views[int(rng.integers(0, len(views)))]

            viewmat_t = torch.tensor(view.viewmat, dtype=torch.float32, device=device).unsqueeze(0)
            K_t = torch.tensor(view.K, dtype=torch.float32, device=device).unsqueeze(0)
            gt_rgb = torch.from_numpy(view.rgb_u8).to(device=device, dtype=torch.float32) / 255.0
            gt_mask = torch.from_numpy(view.mask_u8).to(device=device, dtype=torch.float32) / 255.0

            bg_val = bg_palette[int(rng.integers(0, len(bg_palette)))]
            bg_color = torch.full((1, 1, 3), bg_val, dtype=torch.float32, device=device)

            # Progressive SH degree: 0 -> 1 (step 1000) -> 2 (step 2000)
            active_sh = min(self.config.sh_degree, step // 1000)
            colors_sh = torch.cat([params["sh0"], params["sh_rest"]], dim=1)  # (N, K, 3)
            quats_norm = F.normalize(params["quats"], dim=-1, eps=1e-6)
            scales_act = torch.exp(torch.clamp(params["scales"], min=-10.0, max=2.0))
            opacities_act = torch.sigmoid(params["opacities"])

            out = rasterization_2dgs(
                means=params["means"],
                quats=quats_norm,
                scales=scales_act,
                opacities=opacities_act,
                colors=colors_sh,
                viewmats=viewmat_t,
                Ks=K_t,
                width=view.width,
                height=view.height,
                sh_degree=active_sh,
                render_mode="RGB+ED",
                distloss=True,
                packed=self.config.packed,
            )
            render_colors, render_alphas, render_normals, surf_normals, render_distort, _render_median, info = out

            # gsplat 1.5.3 rasterization_2dgs writes 2D densification gradients to info["gradient_2dgs"]
            # (info["means2d"].grad is identically 0 in 2DGS!).
            grad_key = "gradient_2dgs" if "gradient_2dgs" in info else "means2d"
            if step <= densify_until and grad_key in info and info[grad_key].requires_grad:
                info[grad_key].retain_grad()

            render_rgb = render_colors[0, ..., :3]
            alpha_map = render_alphas[0]
            rn_map = (
                render_normals[0]
                if (render_normals is not None and render_normals.ndim == 4)
                else render_normals
            )
            sn_map = (
                surf_normals[0]
                if (surf_normals is not None and surf_normals.ndim == 4)
                else surf_normals
            )
            dist_map = (
                render_distort[0]
                if (render_distort is not None and render_distort.ndim == 4)
                else render_distort
            )

            loss, metrics = compute_2dgs_loss(
                render_rgb=render_rgb,
                render_alphas=alpha_map,
                gt_rgb=gt_rgb,
                gt_mask=gt_mask,
                bg_color=bg_color,
                step=step,
                config=self.config,
                render_normals=rn_map,
                surf_normals=sn_map,
                render_distort=dist_map,
            )

            optimizer.zero_grad(set_to_none=True)
            loss.backward()

            if step <= densify_until and grad_key in info and info[grad_key].grad is not None:
                with torch.no_grad():
                    grads = info[grad_key].grad.detach().clone()
                    # Scale pixel-space gradients to NDC [-1, 1] matching grad_threshold=2e-4
                    grads[..., 0] *= float(view.width) / 2.0
                    grads[..., 1] *= float(view.height) / 2.0
                    if self.config.packed and "gaussian_ids" in info and info["gaussian_ids"] is not None:
                        g_ids = info["gaussian_ids"]
                        g_norm = torch.norm(grads[..., :2], dim=-1).reshape(-1)
                        grad_accum.index_add_(0, g_ids, g_norm)
                        grad_denom.index_add_(0, g_ids, torch.ones_like(g_norm, dtype=torch.float32))
                    elif "radii" in info and info["radii"] is not None:
                        sel = (info["radii"] > 0.0).all(dim=-1)  # (C, N)
                        g_ids = torch.where(sel)[1]
                        if len(g_ids) > 0:
                            g_norm = torch.norm(grads[sel][..., :2], dim=-1)
                            grad_accum.index_add_(0, g_ids, g_norm)
                            grad_denom.index_add_(0, g_ids, torch.ones_like(g_norm, dtype=torch.float32))
                    else:
                        g_norm = torch.norm(grads[..., :2], dim=-1).reshape(-1)
                        if len(g_norm) == len(grad_accum):
                            grad_accum += g_norm
                            grad_denom += 1.0

            optimizer.step()
            last_loss = metrics["total"]

            # Adaptive densification & pruning every 250 steps (capped at 150k surfels)
            if (
                step >= self.config.densify_from_iter
                and step <= densify_until
                and step % self.config.densify_interval == 0
            ):
                prune_low_opacity = (step - last_opacity_reset) > self.config.densify_interval
                params, grad_accum, grad_denom = self._densify_and_prune(
                    params=params,
                    grad_accum=grad_accum,
                    grad_denom=grad_denom,
                    object_radius=obj_radius,
                    device=device,
                    prune_low_opacity=prune_low_opacity,
                )
                optimizer = _make_optimizer(params, step_idx=step)

            if (
                step > 0
                and step < densify_until
                and step % self.config.opacity_reset_interval == 0
            ):
                with torch.no_grad():
                    max_reset = torch.logit(torch.tensor(0.05, device=device))
                    params["opacities"].data = torch.minimum(params["opacities"].data, max_reset)
                    last_opacity_reset = step

            if step == 1 or step == total_iters or step % self.config.log_interval == 0:
                vram_mib = torch.cuda.memory_allocated(device) / (1024.0 * 1024.0)
                logger.info(
                    "[2DGS] Step %d/%d | loss=%.4f | photo=%.4f | mask=%.4f | norm=%.4f | dist=%.4f | surfels=%d | vram=%.0fMiB",
                    step,
                    total_iters,
                    metrics["total"],
                    metrics["photo"],
                    metrics["mask"],
                    metrics["normal"],
                    metrics["dist"],
                    len(params["means"]),
                    vram_mib,
                )

        peak_vram_mib = torch.cuda.max_memory_allocated(device) / (1024.0 * 1024.0)
        torch.cuda.empty_cache()

        model = Trained2DGSModel(
            means=params["means"].detach(),
            scales=params["scales"].detach(),
            quats=F.normalize(params["quats"].detach(), dim=-1, eps=1e-6),
            opacities=params["opacities"].detach(),
            sh0=params["sh0"].detach(),
            sh_rest=params["sh_rest"].detach(),
            sh_degree=self.config.sh_degree,
            views=views,
            final_loss=last_loss,
            num_surfels=len(params["means"]),
            scene_radius=obj_radius,
            object_center=obj_center,
            object_radius=obj_radius,
            init_surfels=n_init,
            iterations=total_iters,
            peak_vram_mib=peak_vram_mib,
        )

        if debug_dir is not None:
            saved = self.save_debug_renders(model, debug_dir)
            model.debug_render_paths = [str(p) for p in saved]

        return model

    def _densify_and_prune(
        self,
        params: dict[str, Any],
        grad_accum: Any,
        grad_denom: Any,
        object_radius: float,
        device: Any,
        *,
        prune_low_opacity: bool = True,
    ) -> tuple[dict[str, Any], Any, Any]:
        """Clone/split high-gradient surfels under 150k cap and prune low-opacity / oversized surfels."""
        import torch

        with torch.no_grad():
            avg_grad = grad_accum / torch.clamp(grad_denom, min=1.0)
            scales_act = torch.exp(torch.clamp(params["scales"], min=-10.0, max=2.0))
            max_scale = scales_act.max(dim=-1).values
            opacities_act = torch.sigmoid(params["opacities"])

            high_grad = avg_grad >= self.config.grad_threshold
            split_thresh = 0.015 * float(object_radius)
            clone_mask = high_grad & (max_scale <= split_thresh)
            split_mask = high_grad & (max_scale > split_thresh)

            too_big = max_scale > (self.config.max_scale_ratio * float(object_radius))
            if prune_low_opacity:
                keep_mask = (opacities_act >= self.config.min_opacity) & (~too_big)
            else:
                keep_mask = ~too_big
            if int(keep_mask.sum().item()) < 64:
                keep_mask = torch.ones_like(keep_mask, dtype=torch.bool)

            # Shrink split parents in-place on the kept copy before appending jittered twins
            kept_scales = params["scales"].detach().clone()
            split_kept_mask = split_mask & keep_mask
            if bool(split_kept_mask.any()):
                kept_scales[split_kept_mask] -= math.log(1.6)

            base_kept = {
                k: (kept_scales[keep_mask] if k == "scales" else params[k].detach()[keep_mask])
                for k in params
            }
            current_count = len(base_kept["means"])
            budget = max(0, self.config.max_gaussians - current_count)

            add_parts: dict[str, list[Any]] = {k: [base_kept[k]] for k in params}

            if budget > 0:
                clone_idx = torch.nonzero(clone_mask & keep_mask, as_tuple=False).reshape(-1)
                if len(clone_idx) > 0:
                    order = torch.argsort(avg_grad[clone_idx], descending=True)
                    clone_idx = clone_idx[order]
                    take = min(len(clone_idx), budget // 2 if int(split_kept_mask.sum().item()) > 0 else budget)
                    if take > 0:
                        sel = clone_idx[:take]
                        for k in params:
                            add_parts[k].append(params[k].detach()[sel].clone())
                        budget -= take

                split_idx = torch.nonzero(split_kept_mask, as_tuple=False).reshape(-1)
                if len(split_idx) > 0 and budget > 0:
                    order = torch.argsort(avg_grad[split_idx], descending=True)
                    split_idx = split_idx[order]
                    take = min(len(split_idx), budget)
                    sel = split_idx[:take]
                    std = scales_act[sel] * 0.5
                    jitter = torch.randn_like(params["means"][sel]) * std
                    new_means = params["means"].detach()[sel] + jitter
                    new_scales = params["scales"].detach()[sel] - math.log(1.6)
                    add_parts["means"].append(new_means)
                    add_parts["scales"].append(new_scales)
                    for k in ("quats", "opacities", "sh0", "sh_rest"):
                        add_parts[k].append(params[k].detach()[sel].clone())

            new_params = {
                k: torch.nn.Parameter(torch.cat(add_parts[k], dim=0).contiguous())
                for k in params
            }
            new_n = len(new_params["means"])
            return (
                new_params,
                torch.zeros(new_n, dtype=torch.float32, device=device),
                torch.zeros(new_n, dtype=torch.float32, device=device),
            )

    def render_views_for_tsdf(
        self,
        model: Trained2DGSModel,
    ) -> tuple[
        list[np.ndarray],
        list[np.ndarray],
        list[np.ndarray],
        list[np.ndarray],
        list[np.ndarray],
        list[np.ndarray],
    ]:
        """Render median camera-space Z-depth, RGB, and alpha across all valid views for TSDF."""
        import torch
        import torch.nn.functional as F
        from gsplat import rasterization_2dgs

        device = model.means.device
        colors_sh = torch.cat([model.sh0, model.sh_rest], dim=1)
        quats_norm = F.normalize(model.quats, dim=-1, eps=1e-6)
        scales_act = torch.exp(torch.clamp(model.scales, min=-10.0, max=2.0))
        opacities_act = torch.sigmoid(model.opacities)

        depths: list[np.ndarray] = []
        rgbs: list[np.ndarray] = []
        alphas: list[np.ndarray] = []
        masks: list[np.ndarray] = []
        intrinsics: list[np.ndarray] = []
        extrinsics: list[np.ndarray] = []

        with torch.no_grad():
            for view in model.views:
                viewmat_t = torch.tensor(view.viewmat, dtype=torch.float32, device=device).unsqueeze(0)
                K_t = torch.tensor(view.K, dtype=torch.float32, device=device).unsqueeze(0)

                out = rasterization_2dgs(
                    means=model.means,
                    quats=quats_norm,
                    scales=scales_act,
                    opacities=opacities_act,
                    colors=colors_sh,
                    viewmats=viewmat_t,
                    Ks=K_t,
                    width=view.width,
                    height=view.height,
                    sh_degree=model.sh_degree,
                    render_mode="RGB+ED",
                    depth_mode="median",
                    distloss=False,
                    packed=self.config.packed,
                )
                render_colors, render_alphas, _rn, _sn, _dist, render_median, _info = out

                rgb_np = (
                    torch.clamp(render_colors[0, ..., :3], 0.0, 1.0).cpu().numpy() * 255.0
                ).astype(np.uint8)
                alpha_np = render_alphas[0, ..., 0].cpu().numpy().astype(np.float32)

                if render_median is not None:
                    depth_tensor = render_median[0, ..., 0] if render_median.ndim == 4 else render_median[0]
                else:
                    depth_tensor = render_colors[0, ..., 3]
                depth_np = depth_tensor.cpu().numpy().astype(np.float32)

                depths.append(depth_np)
                rgbs.append(rgb_np)
                alphas.append(alpha_np)
                masks.append(view.mask_u8)
                intrinsics.append(view.K)
                extrinsics.append(view.viewmat)

        torch.cuda.empty_cache()
        return depths, rgbs, alphas, masks, intrinsics, extrinsics

    def save_debug_renders(
        self,
        model: Trained2DGSModel,
        output_dir: Path | str,
    ) -> list[Path]:
        """Save 3 horizontal 4-panel convergence PNGs (view_0, view_mid, view_last) into output_dir."""
        import torch
        import torch.nn.functional as F
        from gsplat import rasterization_2dgs

        if not model.views:
            return []

        out_dir = Path(output_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        n_views = len(model.views)
        targets = [
            ("view_0.png", 0),
            ("view_mid.png", n_views // 2),
            ("view_last.png", n_views - 1),
        ]

        device = model.means.device
        colors_sh = torch.cat([model.sh0, model.sh_rest], dim=1)
        quats_norm = F.normalize(model.quats, dim=-1, eps=1e-6)
        scales_act = torch.exp(torch.clamp(model.scales, min=-10.0, max=2.0))
        opacities_act = torch.sigmoid(model.opacities)

        saved: list[Path] = []
        with torch.no_grad():
            for fname, v_idx in targets:
                view = model.views[v_idx]
                viewmat_t = torch.tensor(view.viewmat, dtype=torch.float32, device=device).unsqueeze(0)
                K_t = torch.tensor(view.K, dtype=torch.float32, device=device).unsqueeze(0)

                out = rasterization_2dgs(
                    means=model.means,
                    quats=quats_norm,
                    scales=scales_act,
                    opacities=opacities_act,
                    colors=colors_sh,
                    viewmats=viewmat_t,
                    Ks=K_t,
                    width=view.width,
                    height=view.height,
                    sh_degree=model.sh_degree,
                    render_mode="RGB+ED",
                    depth_mode="median",
                    distloss=False,
                    packed=self.config.packed,
                )
                render_colors, render_alphas, render_normals, _sn, _dist, render_median, _info = out
                rgb_np = (
                    torch.clamp(render_colors[0, ..., :3], 0.0, 1.0).cpu().numpy() * 255.0
                ).astype(np.uint8)
                alpha_np = render_alphas[0, ..., 0].cpu().numpy().astype(np.float32)
                if render_median is not None:
                    depth_t = render_median[0, ..., 0] if render_median.ndim == 4 else render_median[0]
                else:
                    depth_t = render_colors[0, ..., 3]
                depth_np = depth_t.cpu().numpy().astype(np.float32)

                normals_np: Optional[np.ndarray] = None
                if render_normals is not None:
                    rn_t = render_normals[0] if render_normals.ndim == 4 else render_normals
                    normals_np = rn_t.cpu().numpy().astype(np.float32)

                panel = compose_debug_panel(
                    view.rgb_u8,
                    view.mask_u8,
                    rgb_np,
                    depth_np,
                    render_normals=normals_np,
                    render_alpha=alpha_np,
                )
                dest = out_dir / fname
                cv2.imwrite(str(dest), panel)
                saved.append(dest)

        logger.info("[2DGS] Saved %d 4-panel diagnostic convergence renders to %s", len(saved), out_dir)
        return saved
