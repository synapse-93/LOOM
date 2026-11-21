"""Foreground subject isolation and background clutter elimination on canonically aligned point clouds."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Tuple, Union

import numpy as np
import trimesh

from loom.geometry.alignment import read_ply_with_normals, write_ply_with_normals

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SegmentationResult:
    """Diagnostic metrics and output artifact paths from foreground segmentation."""

    points_before: int
    points_after: int
    sub_table_points_removed: int
    background_points_removed: int
    object_center_xy: tuple[float, float]
    object_radius: float
    crop_radius: float
    output_path: Optional[Path] = None


class ForegroundSegmenter:
    """Isolates the foreground object resting on a canonical support plane (Z=0) from background clutter."""

    def __init__(
        self,
        z_min_cutoff: float = -0.005,
        z_elevated_cutoff: float = 0.015,
        radial_multiplier: float = 1.30,
        radius_percentile: float = 98.0,
    ) -> None:
        self.z_min_cutoff = z_min_cutoff
        self.z_elevated_cutoff = z_elevated_cutoff
        self.radial_multiplier = radial_multiplier
        self.radius_percentile = radius_percentile

    def segment(
        self,
        point_cloud: Union[Path, str, np.ndarray, trimesh.PointCloud],
        output_path: Optional[Path | str] = None,
        normals: Optional[np.ndarray] = None,
    ) -> Tuple[trimesh.PointCloud, SegmentationResult]:
        """Isolate foreground geometry on a canonically aligned point cloud (Z=0).

        Args:
            point_cloud: Input file path, numpy array, or trimesh.PointCloud.
            output_path: Optional path to export isolated point cloud (.ply).
            normals: Optional (N, 3) float array of vertex normal vectors.

        Returns:
            Tuple of (isolated_point_cloud, SegmentationResult).
        """
        raw_normals = normals
        raw_colors = None
        if isinstance(point_cloud, (str, Path)):
            p = Path(point_cloud).resolve()
            if not p.is_file():
                raise FileNotFoundError(f"Point cloud file not found: {p}")
            if p.suffix.lower() == ".ply":
                pts, loaded_norms, raw_colors = read_ply_with_normals(p)
                if raw_normals is None and np.any(loaded_norms != 0):
                    raw_normals = loaded_norms
                pc = trimesh.PointCloud(vertices=pts, colors=raw_colors)
            else:
                loaded = trimesh.load(str(p))
                if not isinstance(loaded, trimesh.PointCloud):
                    loaded = trimesh.PointCloud(vertices=loaded.vertices)
                pc = loaded
        elif isinstance(point_cloud, trimesh.PointCloud):
            pc = point_cloud.copy()
            if raw_normals is None:
                v_norms = getattr(pc, "vertex_normals", None)
                if v_norms is not None and len(v_norms) == len(pc.vertices):
                    raw_normals = np.asarray(v_norms, dtype=np.float64)
        else:
            pc = trimesh.PointCloud(vertices=np.asarray(point_cloud, dtype=np.float64))

        vertices = np.asarray(pc.vertices, dtype=np.float64)
        orig_count = len(vertices)
        if orig_count == 0:
            res = SegmentationResult(
                points_before=0,
                points_after=0,
                sub_table_points_removed=0,
                background_points_removed=0,
                object_center_xy=(0.0, 0.0),
                object_radius=0.0,
                crop_radius=0.0,
                output_path=None,
            )
            return pc, res

        if raw_colors is None:
            raw_colors = getattr(pc.visual, "vertex_colors", None)
        has_colors = raw_colors is not None and len(raw_colors) == len(vertices)
        has_normals = raw_normals is not None and len(raw_normals) == len(vertices)

        # 1. Discard sub-table noise (Z < z_min_cutoff)
        valid_z_mask = vertices[:, 2] >= self.z_min_cutoff
        sub_table_removed = int(np.sum(~valid_z_mask))
        pts_filtered = vertices[valid_z_mask]
        colors_filtered = raw_colors[valid_z_mask] if has_colors else None
        norms_filtered = raw_normals[valid_z_mask] if has_normals else None

        if len(pts_filtered) == 0:
            logger.warning("All points fell below Z=%f cutoff; preserving original cloud.", self.z_min_cutoff)
            return pc, SegmentationResult(
                points_before=orig_count,
                points_after=orig_count,
                sub_table_points_removed=0,
                background_points_removed=0,
                object_center_xy=(0.0, 0.0),
                object_radius=0.0,
                crop_radius=0.0,
                output_path=None,
            )

        # 2. Identify elevated object points (Z > z_elevated_cutoff)
        elevated_mask = pts_filtered[:, 2] > self.z_elevated_cutoff
        elevated_pts = pts_filtered[elevated_mask]

        if len(elevated_pts) < 10:
            logger.warning("Insufficient elevated points found above Z=%f; applying sub-table cutoff only.", self.z_elevated_cutoff)
            isolated_pc = trimesh.PointCloud(vertices=pts_filtered, colors=colors_filtered)
            out_p = None
            if output_path is not None:
                out_p = Path(output_path).resolve()
                out_p.parent.mkdir(parents=True, exist_ok=True)
                if norms_filtered is not None and len(norms_filtered) == len(pts_filtered):
                    write_ply_with_normals(out_p, pts_filtered, norms_filtered, colors_filtered)
                else:
                    isolated_pc.export(str(out_p))
            return isolated_pc, SegmentationResult(
                points_before=orig_count,
                points_after=len(pts_filtered),
                sub_table_points_removed=sub_table_removed,
                background_points_removed=0,
                object_center_xy=(0.0, 0.0),
                object_radius=0.0,
                crop_radius=0.0,
                output_path=out_p,
            )

        # 3. Cluster elevated points using cKDTree to isolate dominant object from background
        from scipy.spatial import cKDTree

        tree = cKDTree(elevated_pts[:, :2])
        k_val = min(5, len(elevated_pts))
        dists_k, _ = tree.query(elevated_pts[:, :2], k=k_val)
        if dists_k.ndim > 1 and dists_k.shape[1] > 1:
            eps = float(np.percentile(dists_k[:, -1], 90)) * 2.5
        else:
            eps = float(np.percentile(dists_k, 90)) * 2.5
        eps = max(eps, 0.01)

        adj = tree.query_ball_point(elevated_pts[:, :2], r=eps)
        visited: set[int] = set()
        components: list[list[int]] = []
        for i in range(len(elevated_pts)):
            if i in visited:
                continue
            comp = [i]
            visited.add(i)
            queue = [i]
            while queue:
                curr = queue.pop()
                for neighbor in adj[curr]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        comp.append(neighbor)
                        queue.append(neighbor)
            components.append(comp)

        components.sort(key=len, reverse=True)
        primary_comp = components[0]
        obj_pts_xy = elevated_pts[primary_comp, :2]

        center_xy = np.mean(obj_pts_xy, axis=0)
        rad_dists = np.linalg.norm(obj_pts_xy - center_xy, axis=1)
        object_radius = float(np.percentile(rad_dists, self.radius_percentile))
        crop_radius = float(self.radial_multiplier * object_radius)

        # 4. Cylindrical crop around object center of mass
        all_dists_xy = np.linalg.norm(pts_filtered[:, :2] - center_xy, axis=1)
        keep_mask = all_dists_xy <= crop_radius
        bg_removed = int(np.sum(~keep_mask))

        final_pts = pts_filtered[keep_mask]
        final_colors = colors_filtered[keep_mask] if colors_filtered is not None else None
        final_norms = norms_filtered[keep_mask] if norms_filtered is not None else None

        isolated_pc = trimesh.PointCloud(vertices=final_pts, colors=final_colors)

        out_resolved: Optional[Path] = None
        if output_path is not None:
            out_resolved = Path(output_path).resolve()
            out_resolved.parent.mkdir(parents=True, exist_ok=True)
            if final_norms is not None and len(final_norms) == len(final_pts):
                write_ply_with_normals(out_resolved, final_pts, final_norms, final_colors)
            else:
                isolated_pc.export(str(out_resolved))
            logger.info("Exported isolated point cloud to %s (%d points)", out_resolved, len(final_pts))

        logger.info(
            "Foreground segmentation complete: %d -> %d points (sub-table removed=%d, bg removed=%d, center=[%.3f, %.3f], R_crop=%.3f)",
            orig_count,
            len(final_pts),
            sub_table_removed,
            bg_removed,
            center_xy[0],
            center_xy[1],
            crop_radius,
        )

        return isolated_pc, SegmentationResult(
            points_before=orig_count,
            points_after=len(final_pts),
            sub_table_points_removed=sub_table_removed,
            background_points_removed=bg_removed,
            object_center_xy=(float(center_xy[0]), float(center_xy[1])),
            object_radius=object_radius,
            crop_radius=crop_radius,
            output_path=out_resolved,
        )
