"""Masked TSDF volumetric fusion and Marching Cubes mesh extraction around tight 2DGS core bounds."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np

from loom.utils.paths import ensure_directory

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TsdfExtractionConfig:
    """Configuration for high-resolution adaptive masked TSDF volumetric fusion."""

    voxel_divisor: float = 320.0
    trunc_voxel_multiplier: float = 2.5
    alpha_threshold: float = 0.40
    min_surfel_opacity: float = 0.35
    bound_percentile_low: float = 5.0
    bound_percentile_high: float = 95.0
    max_radius_multiplier: float = 1.35
    min_voxel_length: float = 1e-4
    min_depth_clip: float = 0.05
    far_radius_multiplier: float = 1.5
    dbscan_eps_multiplier: float = 0.12
    dbscan_min_points: int = 15
    dbscan_min_cluster_size: int = 200
    gt_mask_dilation_kernel: int = 21
    skip_gt_mask_when_alpha_present: bool = True


@dataclass(frozen=True)
class TsdfExtractionResult:
    """Output summary and diagnostics from TSDF Marching Cubes extraction."""

    mesh_path: Path
    vertex_count: int
    face_count: int
    voxel_length: float
    sdf_trunc: float
    bounding_radius: float
    views_fused: int
    total_registered_poses: int = 0
    bounding_center: tuple[float, float, float] = (0.0, 0.0, 0.0)
    extents: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def to_manifest_dict(self) -> dict[str, Any]:
        return {
            "tight_center": [round(float(c), 6) for c in self.bounding_center],
            "tight_radius": round(float(self.bounding_radius), 6),
            "voxel_length": round(float(self.voxel_length), 6),
            "sdf_trunc": round(float(self.sdf_trunc), 6),
            "views_fused": int(self.views_fused),
            "total_registered_poses": int(self.total_registered_poses or self.views_fused),
            "vertices": int(self.vertex_count),
            "faces": int(self.face_count),
            "extents": [round(float(e), 6) for e in self.extents],
            "raw_mesh_path": str(self.mesh_path),
        }


def compute_foreground_bounding_sphere(
    points: np.ndarray,
    *,
    opacities: Optional[np.ndarray] = None,
    min_opacity: float = 0.35,
    p_low: float = 5.0,
    p_high: float = 95.0,
    max_radius: Optional[float] = None,
    use_dbscan: bool = True,
    dbscan_min_cluster_size: int = 200,
) -> tuple[np.ndarray, float]:
    """Compute tight (center, radius) bounding sphere from high-opacity surfels + DBSCAN/5th-95th trim."""
    pts = np.asarray(points, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 3 or len(pts) == 0:
        raise ValueError(f"Expected non-empty (N, 3) points array, got shape {pts.shape}")

    if opacities is not None:
        op = np.asarray(opacities, dtype=np.float64).reshape(-1)
        valid = op > float(min_opacity)
        if int(np.count_nonzero(valid)) >= 16:
            pts = pts[valid]

    # Optional Open3D DBSCAN core trimming to eliminate isolated floater clouds
    if use_dbscan and len(pts) >= dbscan_min_cluster_size:
        try:
            import open3d as o3d

            # Subsample to <= 20k points for fast O(N log N) DBSCAN bounding estimate
            if len(pts) > 20_000:
                rng = np.random.default_rng(42)
                sample_pts = pts[rng.choice(len(pts), size=20_000, replace=False)]
            else:
                sample_pts = pts

            rough_span = float(np.linalg.norm(np.percentile(sample_pts, 90, axis=0) - np.percentile(sample_pts, 10, axis=0)))
            eps = max(0.06 * rough_span, 1e-3)
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(sample_pts)
            labels = np.asarray(pcd.cluster_dbscan(eps=eps, min_points=15, print_progress=False))
            uniq, counts = np.unique(labels[labels >= 0], return_counts=True)
            if len(uniq) > 0:
                best_idx = int(np.argmax(counts))
                if int(counts[best_idx]) >= dbscan_min_cluster_size:
                    pts = sample_pts[labels == uniq[best_idx]]
        except Exception as exc:
            logger.debug("[TSDF] DBSCAN bounding trim skipped: %s", exc)

    low = np.percentile(pts, p_low, axis=0)
    high = np.percentile(pts, p_high, axis=0)
    center = 0.5 * (low + high)
    radius = float(0.5 * np.linalg.norm(high - low))
    if max_radius is not None and max_radius > 0:
        radius = min(radius, float(max_radius))
    radius = max(radius, 1e-3)
    return center, radius


def mask_depth_map(
    depth_map: np.ndarray,
    gt_mask: Optional[np.ndarray] = None,
    render_alpha: Optional[np.ndarray] = None,
    alpha_threshold: float = 0.40,
    min_depth: float = 0.05,
    max_depth: Optional[float] = None,
    gt_mask_dilation_kernel: int = 21,
    skip_gt_mask_when_alpha_present: bool = True,
) -> np.ndarray:
    """Zero out background, low-alpha, and out-of-range depth pixels before TSDF integration.

    When converged 3D-consistent 2DGS ``render_alpha`` is provided and
    ``skip_gt_mask_when_alpha_present`` is True, background filtering relies on
    ``render_alpha >= alpha_threshold`` so per-frame 2D ``isnet`` mask dropouts never
    re-punch voids into the fused TSDF mesh.
    """
    depth = np.asarray(depth_map, dtype=np.float32).copy()
    if depth.ndim == 3:
        depth = depth[:, :, 0]

    invalid = (~np.isfinite(depth)) | (depth < float(min_depth))
    if max_depth is not None and max_depth > min_depth:
        invalid |= depth > float(max_depth)

    if render_alpha is not None:
        a = np.asarray(render_alpha, dtype=np.float32)
        if a.ndim == 3:
            a = a[:, :, 0]
        invalid |= a < float(alpha_threshold)

    apply_gt = gt_mask is not None and (render_alpha is None or not skip_gt_mask_when_alpha_present)
    if apply_gt:
        m = np.asarray(gt_mask)
        if m.ndim == 3:
            m = m[:, :, 0]
        if render_alpha is not None and int(gt_mask_dilation_kernel) > 1:
            import cv2

            k = int(gt_mask_dilation_kernel)
            if k % 2 == 0:
                k += 1
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
            m = cv2.dilate((m > 0).astype(np.uint8) * 255, kernel)
        invalid |= m <= 0

    depth[invalid] = 0.0
    return depth


class TsdfMeshExtractor:
    """Fuses masked 2DGS median depth maps into a tight sparse TSDF volume and extracts a mesh."""

    def __init__(self, config: Optional[TsdfExtractionConfig] = None) -> None:
        self.config = config or TsdfExtractionConfig()

    def fuse_depth_maps(
        self,
        depth_maps: Sequence[np.ndarray],
        rgb_maps: Sequence[np.ndarray],
        intrinsics: Sequence[np.ndarray],
        extrinsics: Sequence[np.ndarray],
        output_path: Path | str,
        *,
        bounding_center: np.ndarray,
        bounding_radius: float,
        masks: Optional[Sequence[Optional[np.ndarray]]] = None,
        alphas: Optional[Sequence[Optional[np.ndarray]]] = None,
    ) -> TsdfExtractionResult:
        """Integrate masked depth/RGB maps via Open3D sparse TSDF and extract largest cluster."""
        import open3d as o3d
        import open3d.core as o3c

        n_views = len(depth_maps)
        if n_views == 0:
            raise ValueError("Cannot run TSDF fusion with zero depth maps.")

        voxel_length = max(
            float(bounding_radius) / float(self.config.voxel_divisor),
            float(self.config.min_voxel_length),
        )
        sdf_trunc = float(self.config.trunc_voxel_multiplier) * voxel_length
        center = np.asarray(bounding_center, dtype=np.float64).reshape(3)

        logger.info(
            "[TSDF] Initializing sparse TSDF (VoxelBlockGrid CPU): views=%d, tight_radius=%.4f, "
            "voxel_length=%.6f, sdf_trunc=%.6f",
            n_views,
            bounding_radius,
            voxel_length,
            sdf_trunc,
        )

        # Open3D 0.20.0 legacy ScalableTSDFVolume has an upstream 0-triangle regression;
        # Open3D's tensor sparse VoxelBlockGrid on CPU:0 achieves identical sparse TSDF
        # integration with depth_scale=1.0, zero GPU VRAM overhead, and reliable Marching Cubes.
        device = o3c.Device("CPU:0")
        vbg = o3d.t.geometry.VoxelBlockGrid(
            attr_names=("tsdf", "weight", "color"),
            attr_dtypes=(o3c.float32, o3c.float32, o3c.float32),
            attr_channels=((1), (1), (3)),
            voxel_size=voxel_length,
            block_resolution=16,
            block_count=50_000,
            device=device,
        )

        views_fused = 0

        for idx in range(n_views):
            K = np.ascontiguousarray(intrinsics[idx], dtype=np.float64)
            extrinsic = np.ascontiguousarray(extrinsics[idx], dtype=np.float64)

            cam_center = -extrinsic[:3, :3].T @ extrinsic[:3, 3]
            cam_dist = float(np.linalg.norm(cam_center - center))
            far_clip = cam_dist + float(self.config.far_radius_multiplier) * float(bounding_radius)

            gt_mask = masks[idx] if masks is not None else None
            alpha = alphas[idx] if alphas is not None else None
            masked_depth = mask_depth_map(
                depth_maps[idx],
                gt_mask=gt_mask,
                render_alpha=alpha,
                alpha_threshold=self.config.alpha_threshold,
                min_depth=self.config.min_depth_clip,
                max_depth=far_clip,
                gt_mask_dilation_kernel=self.config.gt_mask_dilation_kernel,
                skip_gt_mask_when_alpha_present=self.config.skip_gt_mask_when_alpha_present,
            )
            if not np.any(masked_depth > 0.0):
                continue

            rgb = np.asarray(rgb_maps[idx])
            if np.issubdtype(rgb.dtype, np.floating):
                max_val = float(np.nanmax(rgb))
                rgb_f32 = np.clip(
                    np.nan_to_num(rgb, nan=0.0) / (255.0 if max_val > 1.0 + 1e-6 else 1.0),
                    0.0,
                    1.0,
                ).astype(np.float32)
            else:
                rgb_f32 = (np.clip(rgb, 0, 255).astype(np.float32)) / 255.0

            rgb_contig = np.ascontiguousarray(rgb_f32, dtype=np.float32)
            depth_contig = np.ascontiguousarray(masked_depth, dtype=np.float32)

            if views_fused == 0:
                nz = depth_contig[depth_contig > 0.0]
                logger.info(
                    "[TSDF] View 0 Z-depth audit: min=%.4f, median=%.4f, max=%.4f | cam_dist=%.4f | clip=[%.2f, %.4f] (pixels=%d)",
                    float(np.min(nz)),
                    float(np.median(nz)),
                    float(np.max(nz)),
                    cam_dist,
                    float(self.config.min_depth_clip),
                    far_clip,
                    int(nz.size),
                )

            t_depth = o3d.t.geometry.Image(o3c.Tensor(depth_contig, device=device))
            t_color = o3d.t.geometry.Image(o3c.Tensor(rgb_contig, device=device))
            t_intrinsic = o3c.Tensor(K, dtype=o3c.float64, device=device)
            t_extrinsic = o3c.Tensor(extrinsic, dtype=o3c.float64, device=device)

            frustum_block_coords = vbg.compute_unique_block_coordinates(
                t_depth,
                t_intrinsic,
                t_extrinsic,
                depth_scale=1.0,
                depth_max=float(far_clip + sdf_trunc),
            )
            vbg.integrate(
                frustum_block_coords,
                t_depth,
                t_color,
                t_intrinsic,
                t_extrinsic,
                depth_scale=1.0,
                depth_max=float(far_clip + sdf_trunc),
                trunc_voxel_multiplier=float(self.config.trunc_voxel_multiplier),
            )
            views_fused += 1

            if idx == 0 or (idx + 1) == n_views or (idx + 1) % 15 == 0:
                logger.info("[TSDF] Integrated view %d/%d", idx + 1, n_views)

        if views_fused == 0:
            raise RuntimeError("TSDF fusion failed: zero views contained valid masked depth pixels.")

        logger.info(
            "[TSDF] Fused %d / %d registered poses (alpha_threshold=%.2f); running Marching Cubes surface extraction...",
            views_fused,
            n_views,
            float(self.config.alpha_threshold),
        )
        mesh = vbg.extract_triangle_mesh().to_legacy()
        if len(mesh.triangles) == 0 or len(mesh.vertices) == 0:
            raise RuntimeError("TSDF Marching Cubes extracted an empty triangle mesh (0 faces).")

        triangle_clusters, cluster_n_triangles, _ = mesh.cluster_connected_triangles()
        triangle_clusters_arr = np.asarray(triangle_clusters)
        cluster_n_triangles_arr = np.asarray(cluster_n_triangles)
        if len(cluster_n_triangles_arr) > 1:
            largest_cluster_idx = int(np.argmax(cluster_n_triangles_arr))
            mesh.remove_triangles_by_mask(triangle_clusters_arr != largest_cluster_idx)
            mesh.remove_unreferenced_vertices()
            logger.info(
                "[TSDF] Kept largest connected component (%d clusters pruned -> %d faces)",
                len(cluster_n_triangles_arr) - 1,
                len(mesh.triangles),
            )

        mesh.compute_vertex_normals()

        out_path = Path(output_path).resolve()
        ensure_directory(out_path.parent)
        o3d.io.write_triangle_mesh(str(out_path), mesh, write_ascii=False)

        v_arr = np.asarray(mesh.vertices, dtype=np.float64)
        ext = np.ptp(v_arr, axis=0) if len(v_arr) > 0 else np.zeros(3)
        v_count = len(mesh.vertices)
        f_count = len(mesh.triangles)
        logger.info(
            "[TSDF] Extracted raw 2DGS mesh -> %s (%d vertices, %d faces, extents=[%.4f, %.4f, %.4f])",
            out_path,
            v_count,
            f_count,
            float(ext[0]),
            float(ext[1]),
            float(ext[2]),
        )
        return TsdfExtractionResult(
            mesh_path=out_path,
            vertex_count=v_count,
            face_count=f_count,
            voxel_length=voxel_length,
            sdf_trunc=sdf_trunc,
            bounding_radius=float(bounding_radius),
            views_fused=views_fused,
            total_registered_poses=n_views,
            bounding_center=(float(center[0]), float(center[1]), float(center[2])),
            extents=(float(ext[0]), float(ext[1]), float(ext[2])),
        )

    def extract_from_2dgs(
        self,
        reconstructor: Any,
        trained_model: Any,
        output_path: Path | str,
    ) -> TsdfExtractionResult:
        """Render median depth + RGB maps from ALL registered poses and fuse into tight TSDF mesh."""
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        all_poses = getattr(trained_model, "all_poses", None)
        n_render_poses = len(all_poses) if all_poses else len(trained_model.views)
        logger.info(
            "[TSDF] Rendering masked median depth maps across %d registered poses (%d trained valid views)...",
            n_render_poses,
            len(trained_model.views),
        )
        rendered_depths, rendered_rgbs, rendered_alphas, masks, intrinsics, extrinsics = (
            reconstructor.render_views_for_tsdf(trained_model)
        )

        obj_radius = getattr(trained_model, "object_radius", None) or getattr(
            trained_model, "scene_radius", None
        )
        max_rad = (
            float(self.config.max_radius_multiplier) * float(obj_radius)
            if obj_radius is not None and float(obj_radius) > 0
            else None
        )
        center, radius = compute_foreground_bounding_sphere(
            trained_model.means_np,
            opacities=trained_model.opacities_np,
            min_opacity=self.config.min_surfel_opacity,
            p_low=self.config.bound_percentile_low,
            p_high=self.config.bound_percentile_high,
            max_radius=max_rad,
            use_dbscan=True,
            dbscan_min_cluster_size=self.config.dbscan_min_cluster_size,
        )

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        return self.fuse_depth_maps(
            depth_maps=rendered_depths,
            rgb_maps=rendered_rgbs,
            intrinsics=intrinsics,
            extrinsics=extrinsics,
            output_path=output_path,
            bounding_center=center,
            bounding_radius=radius,
            masks=masks,
            alphas=rendered_alphas,
        )
