"""Deterministic invalid, degenerate, and unreferenced geometry cleanup."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import numpy as np
from scipy.spatial import cKDTree
import trimesh

from loom.config.models import MeshConfig
from loom.mesh.models import CleanupActionResult

logger = logging.getLogger(__name__)


class MeshCleaner:
    """Removes NaN/inf vertices, invalid indices, zero-area degenerate faces, and duplicate geometry."""

    def __init__(self, config: Optional[MeshConfig] = None) -> None:
        self.config = config or MeshConfig()

    def clean_mesh(
        self,
        mesh: Any = None,
        config: Optional[MeshConfig] = None,
    ) -> tuple[trimesh.Trimesh, CleanupActionResult]:
        """Clean mesh (supports instance or class call)."""
        if isinstance(self, MeshCleaner):
            target_mesh = mesh
            target_config = config or self.config
        else:
            target_mesh = self
            target_config = mesh if isinstance(mesh, MeshConfig) else (config or MeshConfig())
        return MeshCleaner.clean(target_mesh, target_config)

    @classmethod
    def clean(
        cls,
        mesh: trimesh.Trimesh,
        config: MeshConfig,
    ) -> tuple[trimesh.Trimesh, CleanupActionResult]:

        """Perform comprehensive deterministic cleanup of invalid, degenerate, and unreferenced geometry."""
        vertices = np.asarray(mesh.vertices, dtype=np.float64)
        faces = np.asarray(mesh.faces, dtype=np.int64)

        orig_v_count = len(vertices)
        orig_f_count = len(faces)

        invalid_vertices_removed = 0
        invalid_faces_removed = 0
        degenerate_faces_removed = 0
        duplicate_faces_removed = 0
        unreferenced_vertices_removed = 0

        # Step 1: Remove NaN and Infinite vertices
        nan_or_inf_mask = np.isnan(vertices).any(axis=1) | np.isinf(vertices).any(axis=1)
        invalid_v_indices = set(np.where(nan_or_inf_mask)[0])
        invalid_vertices_removed = len(invalid_v_indices)

        if invalid_vertices_removed > 0:
            logger.warning("Removing %d NaN or Infinite vertices and adjacent faces.", invalid_vertices_removed)
            valid_v_mask = ~nan_or_inf_mask
            # Build old-to-new vertex mapping (-1 for dropped)
            old_to_new = np.full(orig_v_count, -1, dtype=np.int64)
            old_to_new[valid_v_mask] = np.arange(np.sum(valid_v_mask))
            vertices = vertices[valid_v_mask]

            # Keep faces only if all 3 vertices are valid
            if len(faces) > 0:
                face_valid = ~np.isin(faces[:, 0], list(invalid_v_indices)) & \
                             ~np.isin(faces[:, 1], list(invalid_v_indices)) & \
                             ~np.isin(faces[:, 2], list(invalid_v_indices))
                dropped_faces = np.sum(~face_valid)
                invalid_faces_removed += int(dropped_faces)
                faces = old_to_new[faces[face_valid]]

        # Step 2: Remove invalid face indices
        if len(faces) > 0 and len(vertices) > 0:
            v_len = len(vertices)
            oob = (faces < 0) | (faces >= v_len)
            repeated = (
                (faces[:, 0] == faces[:, 1])
                | (faces[:, 1] == faces[:, 2])
                | (faces[:, 0] == faces[:, 2])
            )
            invalid_face_mask = np.any(oob, axis=1) | repeated
            invalid_f_count = int(np.sum(invalid_face_mask))
            if invalid_f_count > 0:
                logger.warning("Removing %d invalid or collapsed faces.", invalid_f_count)
                invalid_faces_removed += invalid_f_count
                faces = faces[~invalid_face_mask]

        # Step 3: Remove degenerate faces (zero-area triangles)
        if config.remove_degenerate_faces and len(faces) > 0 and len(vertices) > 0:
            v0 = vertices[faces[:, 0]]
            v1 = vertices[faces[:, 1]]
            v2 = vertices[faces[:, 2]]
            cross = np.cross(v1 - v0, v2 - v0)
            areas = 0.5 * np.linalg.norm(cross, axis=1)
            thresh = getattr(config, "degenerate_area_threshold", 1e-7)
            degenerate_mask = np.isnan(areas) | (areas <= thresh)
            degen_count = int(np.sum(degenerate_mask))
            if degen_count > 0:
                logger.info("Removing %d degenerate (zero-area) faces.", degen_count)
                degenerate_faces_removed += degen_count
                faces = faces[~degenerate_mask]

        # Step 4: Remove duplicate faces
        if config.remove_duplicate_faces and len(faces) > 0:
            sorted_f = np.sort(faces, axis=1)
            _, unique_indices = np.unique(sorted_f, axis=0, return_index=True)
            dup_count = len(faces) - len(unique_indices)
            if dup_count > 0:
                logger.info("Removing %d duplicate faces.", dup_count)
                duplicate_faces_removed += dup_count
                faces = faces[np.sort(unique_indices)]

        # Step 5: Remove unreferenced vertices
        if config.remove_unreferenced_vertices and len(vertices) > 0:
            if len(faces) > 0:
                unique_used = np.unique(faces)
                unref_count = len(vertices) - len(unique_used)
                if unref_count > 0:
                    logger.info("Removing %d unreferenced (orphaned) vertices.", unref_count)
                    unreferenced_vertices_removed += unref_count
                    remap = np.full(len(vertices), -1, dtype=np.int64)
                    remap[unique_used] = np.arange(len(unique_used))
                    vertices = vertices[unique_used]
                    faces = remap[faces]
            else:
                # No faces remain; unreferenced count is all vertices
                unreferenced_vertices_removed += len(vertices)
                vertices = np.empty((0, 3), dtype=np.float64)

        # Construct new cleaned mesh with strictly preserved coordinates
        cleaned_mesh = trimesh.Trimesh(
            vertices=vertices,
            faces=faces,
            process=False,  # Keep process=False to avoid unwanted auto-transformations
        )

        action_result = CleanupActionResult(
            invalid_vertices_removed=invalid_vertices_removed,
            invalid_faces_removed=invalid_faces_removed,
            degenerate_faces_removed=degenerate_faces_removed,
            duplicate_faces_removed=duplicate_faces_removed,
            unreferenced_vertices_removed=unreferenced_vertices_removed,
            vertices_before=orig_v_count,
            vertices_after=len(cleaned_mesh.vertices),
            faces_before=orig_f_count,
            faces_after=len(cleaned_mesh.faces),
        )


        logger.info(
            "Mesh cleanup complete: vertices %d -> %d, faces %d -> %d (invalid_v: %d, invalid_f: %d, degen: %d, dup: %d, unref: %d)",
            orig_v_count,
            len(cleaned_mesh.vertices),
            orig_f_count,
            len(cleaned_mesh.faces),
            invalid_vertices_removed,
            invalid_faces_removed,
            degenerate_faces_removed,
            duplicate_faces_removed,
            unreferenced_vertices_removed,
        )

        return cleaned_mesh, action_result

    @classmethod
    def remove_floor_plane(
        cls,
        mesh: trimesh.Trimesh,
        normal_tolerance_deg: float = 20.0,
        bottom_percentile: float = 0.15,
        distance_threshold: Optional[float] = None,
        max_iterations: int = 1000,
        output_path: Optional[Path | str] = None,
    ) -> tuple[trimesh.Trimesh, dict[str, Any]]:
        """Identify dominant horizontal plane using RANSAC within normal tolerance and clip floor faces.

        Args:
            mesh: Input trimesh geometry.
            normal_tolerance_deg: Maximum angular deviation in degrees from the vertical Z-up axis.
            bottom_percentile: Bounding box percentile (0.0 to 1.0) defining the lower elevation candidate zone.
            distance_threshold: Maximum distance to the plane for a point/face to be considered an inlier.
                                If None, adaptively computed from bounding box dimensions.
            max_iterations: Maximum RANSAC sampling iterations.
            output_path: Optional path to export intermediate mesh (e.g. 04_floor_removed.ply).

        Returns:
            Tuple of (cleaned_mesh, result_dict) where result_dict contains floor isolation statistics.
        """
        vertices = np.asarray(mesh.vertices, dtype=np.float64)
        faces = np.asarray(mesh.faces, dtype=np.int64)

        if len(faces) == 0 or len(vertices) == 0:
            return mesh, {
                "floor_detected": False,
                "faces_removed": 0,
                "inlier_count": 0,
                "floor_plane": None,
            }

        z_min = float(np.min(vertices[:, 2]))
        z_max = float(np.max(vertices[:, 2]))
        z_span = z_max - z_min

        if z_span <= 1e-8:
            return mesh, {
                "floor_detected": False,
                "faces_removed": 0,
                "inlier_count": 0,
                "floor_plane": None,
            }

        z_thresh = z_min + bottom_percentile * z_span
        cos_tol = float(np.cos(np.radians(normal_tolerance_deg)))
        d_thresh = float(distance_threshold) if distance_threshold is not None else max(0.01 * z_span, 1e-3)

        cand_mask = vertices[:, 2] <= z_thresh
        cand_indices = np.where(cand_mask)[0]
        if len(cand_indices) < 3:
            logger.info("Fewer than 3 candidate vertices in bottom percentile; skipping floor removal.")
            return mesh, {
                "floor_detected": False,
                "faces_removed": 0,
                "inlier_count": 0,
                "floor_plane": None,
            }

        cand_pts = vertices[cand_indices]
        rng = np.random.default_rng(42)
        best_inliers: np.ndarray = np.array([], dtype=int)
        best_normal: Optional[np.ndarray] = None
        best_d: float = 0.0

        for _ in range(max_iterations):
            idx = rng.choice(len(cand_pts), size=3, replace=False)
            p0, p1, p2 = cand_pts[idx[0]], cand_pts[idx[1]], cand_pts[idx[2]]
            norm = np.cross(p1 - p0, p2 - p0)
            norm_len = float(np.linalg.norm(norm))
            if norm_len < 1e-8:
                continue
            norm = norm / norm_len
            if abs(norm[2]) < cos_tol:
                continue
            if norm[2] < 0:
                norm = -norm
            d = -float(np.dot(norm, p0))
            dists = np.abs(np.dot(cand_pts, norm) + d)
            inliers = np.where(dists <= d_thresh)[0]
            if len(inliers) > len(best_inliers):
                best_inliers = inliers
                best_normal = norm
                best_d = d

        if best_normal is None or len(best_inliers) < 3:
            logger.info("No dominant horizontal plane detected within normal tolerance %.1f deg.", normal_tolerance_deg)
            return mesh, {
                "floor_detected": False,
                "faces_removed": 0,
                "inlier_count": 0,
                "floor_plane": None,
            }

        # Refine plane via SVD on inliers
        inlier_pts = cand_pts[best_inliers]
        center = np.mean(inlier_pts, axis=0)
        shifted = inlier_pts - center
        _, _, vh = np.linalg.svd(shifted)
        refined_norm = vh[2]
        if refined_norm[2] < 0:
            refined_norm = -refined_norm
        if abs(refined_norm[2]) >= cos_tol:
            best_normal = refined_norm
            best_d = -float(np.dot(best_normal, center))

        # Floor face identification
        face_verts = vertices[faces]  # (F, 3, 3)
        face_centroids = np.mean(face_verts, axis=1)  # (F, 3)

        below_z = face_centroids[:, 2] <= (z_thresh + d_thresh)
        dists_to_plane = np.abs(np.dot(face_centroids, best_normal) + best_d)
        on_plane = dists_to_plane <= d_thresh

        fn0 = face_verts[:, 1] - face_verts[:, 0]
        fn1 = face_verts[:, 2] - face_verts[:, 0]
        fn_cross = np.cross(fn0, fn1)
        fn_len = np.linalg.norm(fn_cross, axis=1, keepdims=True)
        valid_fn = (fn_len[:, 0] > 1e-8)
        fn_norm = np.zeros_like(fn_cross)
        fn_norm[valid_fn] = fn_cross[valid_fn] / fn_len[valid_fn]
        normal_aligned = np.abs(fn_norm[:, 2]) >= cos_tol

        v_dists = np.abs(np.dot(face_verts, best_normal) + best_d)
        all_v_on_plane = np.all(v_dists <= d_thresh, axis=1)
        all_v_below_z = np.all(face_verts[:, :, 2] <= (z_thresh + d_thresh), axis=1)

        floor_face_mask = (below_z & on_plane & normal_aligned) | (all_v_on_plane & all_v_below_z)
        faces_to_remove = int(np.sum(floor_face_mask))

        if faces_to_remove == len(faces):
            logger.warning("Floor plane removal would delete the entire mesh; preserving geometry.")
            return mesh, {
                "floor_detected": True,
                "faces_removed": 0,
                "inlier_count": len(best_inliers),
                "floor_plane": (best_normal.tolist(), best_d),
            }

        remaining_faces = faces[~floor_face_mask]
        cleaned_mesh = trimesh.Trimesh(vertices=vertices, faces=remaining_faces, process=False)
        cleaned_mesh.remove_unreferenced_vertices()

        if output_path is not None:
            out_p = Path(output_path).resolve()
            out_p.parent.mkdir(parents=True, exist_ok=True)
            cleaned_mesh.export(out_p)
            logger.info("Exported floor-removed intermediate mesh to: %s", out_p)

        logger.info(
            "Floor removal complete: removed %d floor faces (inliers=%d, normal=[%.3f, %.3f, %.3f], d=%.4f).",
            faces_to_remove,
            len(best_inliers),
            best_normal[0],
            best_normal[1],
            best_normal[2],
            best_d,
        )

        return cleaned_mesh, {
            "floor_detected": True,
            "faces_removed": faces_to_remove,
            "inlier_count": len(best_inliers),
            "floor_plane": (best_normal.tolist(), best_d),
            "output_path": Path(output_path).resolve() if output_path else None,
        }

    @classmethod
    def isolate_target_component(
        cls,
        mesh: trimesh.Trimesh,
        reference_point: Optional[tuple[float, float, float] | np.ndarray] = None,
        min_faces: int = 50,
        output_path: Optional[Path | str] = None,
    ) -> tuple[trimesh.Trimesh, dict[str, Any]]:
        """Isolate target component using memory-safe connected components.

        Component Selection Logic:
        - Identify components with > 100,000 faces (or > 20% of total mesh faces).
        - Component #0 is the primary object (the shoe).
        - Under NO circumstances should any component with < 1,000 faces be chosen as the target object when large components exist.
        - Extract target mesh cleanly using mesh.submesh([target_face_indices], append=True).

        Args:
            mesh: Input trimesh geometry.
            reference_point: Optional target 3D/2D coordinates. If None, Component #0 is directly selected.
            min_faces: Minimum face threshold when no large components exist.
            output_path: Optional path to export intermediate mesh.

        Returns:
            Tuple of (isolated_mesh, result_dict).
        """
        if len(mesh.faces) == 0:
            return mesh, {"components_before": 0, "components_after": 0, "selected_index": -1}

        from loom.mesh.components import MeshComponentAnalyzer
        face_components = MeshComponentAnalyzer.get_face_components(mesh)
        total_components = len(face_components)

        if total_components <= 1:
            return mesh, {
                "components_before": total_components,
                "components_after": total_components,
                "selected_index": 0 if total_components == 1 else -1,
                "selected_faces": len(mesh.faces),
            }

        total_faces = len(mesh.faces)
        max_faces = len(face_components[0])

        large_component_indices = [
            i for i, c in enumerate(face_components)
            if len(c) > 100_000 or (total_faces >= 10_000 and len(c) > 0.20 * total_faces and len(c) >= 1_000)
        ]
        has_large_components = len(large_component_indices) > 0

        if reference_point is None:
            # Component #0 is the primary object (the shoe)
            best_idx = 0
            min_dist = 0.0
        else:
            ref = np.asarray(reference_point, dtype=np.float64)
            if has_large_components:
                # Under NO circumstances should any component with < 1,000 faces be chosen when large components exist
                eligible = [i for i in large_component_indices if len(face_components[i]) >= 1_000]
                if not eligible:
                    eligible = [0]
            else:
                thresh = min(min_faces, max_faces)
                eligible = [i for i, c in enumerate(face_components) if len(c) >= thresh]
                if not eligible:
                    eligible = [0]

            min_dist = float("inf")
            best_idx = eligible[0]
            for idx in eligible:
                comp = face_components[idx]
                c_faces = mesh.faces[comp]
                c_verts = mesh.vertices[np.unique(c_faces)]
                c = np.mean(c_verts, axis=0)
                dist = float(np.linalg.norm(c[:len(ref)] - ref))
                if dist < min_dist:
                    min_dist = dist
                    best_idx = idx

        target_face_indices = face_components[best_idx]
        target_mesh = mesh.submesh([target_face_indices], append=True)

        if output_path is not None:
            out_p = Path(output_path).resolve()
            out_p.parent.mkdir(parents=True, exist_ok=True)
            target_mesh.export(out_p)
            logger.info("Exported isolated target component to: %s", out_p)

        logger.info(
            "Component isolation: selected component #%d (%d faces, centroid dist=%.4f) out of %d components.",
            best_idx,
            len(target_mesh.faces),
            min_dist,
            total_components,
        )

        return target_mesh, {
            "components_before": total_components,
            "components_after": 1,
            "selected_index": best_idx,
            "selected_faces": len(target_mesh.faces),
            "distance_to_reference": min_dist,
            "output_path": Path(output_path).resolve() if output_path else None,
        }

    @classmethod
    def cull_by_point_cloud_distance(
        cls,
        mesh: trimesh.Trimesh,
        point_cloud: Any,
        max_distance: Optional[float] = None,
        multiplier: float = 3.5,
        sample_size: int = 10000,
        seed: int = 42,
        output_path: Optional[Path | str] = None,
    ) -> tuple[trimesh.Trimesh, dict[str, Any]]:
        """Cull mesh faces that are not grounded by real 3D point cloud points.

        Builds a KDTree on the reconstructed point cloud and discards ungrounded
        air surface artifacts (e.g. Poisson balloons in unobserved volumes).

        Args:
            mesh: Input reconstructed mesh geometry.
            point_cloud: Point cloud representation (Path, string, PointCloud, Trimesh, or (N, 3) array).
            max_distance: Hard distance threshold. If None, computed as multiplier * median 2-NN point spacing.
            multiplier: Spacing multiplier when max_distance is None (default: 3.5).
            sample_size: Number of points to sample for local spacing estimation (default: 10,000).
            seed: Deterministic random seed for sample point selection.
            output_path: Optional destination to export culled mesh.

        Returns:
            Tuple of (culled_mesh, stats_dict).
        """
        # Resolve point cloud vertices
        if isinstance(point_cloud, (str, Path)):
            p = Path(point_cloud).resolve()
            if not p.is_file():
                raise FileNotFoundError(f"Point cloud file does not exist: {p}")
            loaded_pc = trimesh.load(str(p), process=False)
            if isinstance(loaded_pc, trimesh.Scene):
                loaded_pc = trimesh.util.concatenate(list(loaded_pc.geometry.values()))
            pc_pts = np.asarray(loaded_pc.vertices, dtype=np.float64)
        elif hasattr(point_cloud, "vertices"):
            pc_pts = np.asarray(point_cloud.vertices, dtype=np.float64)
        elif isinstance(point_cloud, np.ndarray):
            pc_pts = np.asarray(point_cloud, dtype=np.float64)
        else:
            raise TypeError(f"Unsupported point cloud type: {type(point_cloud)}")

        if len(pc_pts) == 0 or len(mesh.faces) == 0:
            return mesh, {
                "culled": False,
                "faces_before": len(mesh.faces),
                "faces_after": len(mesh.faces),
                "faces_removed": 0,
                "threshold": 0.0,
                "local_spacing": 0.0,
                "output_path": None,
            }

        tree = cKDTree(pc_pts)
        orig_faces_count = len(mesh.faces)

        if max_distance is not None:
            threshold = float(max_distance)
            local_spacing = threshold / multiplier
        else:
            rng = np.random.default_rng(seed)
            sample_count = min(sample_size, len(pc_pts))
            sample_idx = rng.choice(len(pc_pts), size=sample_count, replace=False)
            sample_pts = pc_pts[sample_idx]
            dists_2nn = tree.query(sample_pts, k=2)[0]
            if len(dists_2nn) > 0 and dists_2nn.shape[1] > 1:
                local_spacing = float(np.median(dists_2nn[:, 1]))
            else:
                local_spacing = 0.01
            threshold = multiplier * local_spacing

        mesh_vertices = np.asarray(mesh.vertices, dtype=np.float64)
        v_dists = tree.query(mesh_vertices)[0]
        f_dists = v_dists[mesh.faces]
        keep_faces_mask = f_dists.max(axis=1) <= threshold
        keep_indices = np.where(keep_faces_mask)[0]

        if len(keep_indices) == 0:
            logger.warning("Distance culling would remove all faces (threshold=%.4f); preserving original mesh.", threshold)
            return mesh, {
                "culled": False,
                "faces_before": orig_faces_count,
                "faces_after": orig_faces_count,
                "faces_removed": 0,
                "threshold": threshold,
                "local_spacing": local_spacing,
                "output_path": None,
            }

        culled_mesh = mesh.submesh([keep_indices], append=True)
        faces_removed = orig_faces_count - len(culled_mesh.faces)

        if output_path is not None:
            out_p = Path(output_path).resolve()
            out_p.parent.mkdir(parents=True, exist_ok=True)
            culled_mesh.export(out_p)
            logger.info("Exported point-cloud culled mesh to: %s", out_p)

        logger.info(
            "Point cloud distance culling complete: faces %d -> %d (removed %d faces, threshold=%.5f, spacing=%.5f).",
            orig_faces_count,
            len(culled_mesh.faces),
            faces_removed,
            threshold,
            local_spacing,
        )

        return culled_mesh, {
            "culled": True,
            "faces_before": orig_faces_count,
            "faces_after": len(culled_mesh.faces),
            "faces_removed": faces_removed,
            "threshold": threshold,
            "local_spacing": local_spacing,
            "output_path": Path(output_path).resolve() if output_path else None,
        }

    @classmethod
    def fit_floor_plane_ransac(
        cls,
        mesh: trimesh.Trimesh,
        bottom_percentile: float = 0.15,
        normal_tolerance_deg: float = 15.0,
        distance_threshold: float = 0.01,
        max_iterations: int = 500,
        seed: int = 42,
    ) -> tuple[Optional[np.ndarray], float, float]:
        """Fit a horizontal floor plane to the bottom percentile using RANSAC.

        Args:
            mesh: Input trimesh geometry.
            bottom_percentile: Lower bounding box percentile (0.0 to 1.0) candidate zone.
            normal_tolerance_deg: Angular tolerance from vertical (Z-up) axis.
            distance_threshold: Maximum distance to plane for inlier selection.
            max_iterations: Maximum RANSAC sampling iterations.
            seed: Deterministic random seed for RANSAC sampling.

        Returns:
            Tuple of (normal, d, z_floor) where dot(normal, p) + d = 0, and normal[2] > 0.
            If no plane is detected, returns (None, 0.0, z_min).
        """
        zv = mesh.vertices[:, 2]
        if len(zv) == 0:
            return None, 0.0, 0.0

        z_min = float(np.min(zv))
        z_max = float(np.max(zv))
        z_span = z_max - z_min
        if z_span <= 1e-8:
            return None, 0.0, z_min

        bottom_pts = mesh.vertices[zv <= (z_min + bottom_percentile * z_span)]
        if len(bottom_pts) < 3:
            return None, 0.0, z_min

        cos_tol = float(np.cos(np.radians(normal_tolerance_deg)))
        rng = np.random.default_rng(seed)
        best_inliers: np.ndarray = np.array([], dtype=int)
        best_normal: Optional[np.ndarray] = None
        best_d: float = 0.0

        for _ in range(max_iterations):
            idx = rng.choice(len(bottom_pts), size=3, replace=False)
            p0, p1, p2 = bottom_pts[idx[0]], bottom_pts[idx[1]], bottom_pts[idx[2]]
            n = np.cross(p1 - p0, p2 - p0)
            norm_len = float(np.linalg.norm(n))
            if norm_len < 1e-8:
                continue
            n = n / norm_len
            if abs(n[2]) < cos_tol:
                continue
            if n[2] < 0:
                n = -n
            d = -float(np.dot(n, p0))
            dists = np.abs(np.dot(bottom_pts, n) + d)
            inliers = np.where(dists <= distance_threshold)[0]
            if len(inliers) > len(best_inliers):
                best_inliers = inliers
                best_normal = n
                best_d = d

        if best_normal is None or len(best_inliers) < 3:
            return None, 0.0, z_min

        # SVD refinement on inliers
        inlier_pts = bottom_pts[best_inliers]
        center = np.mean(inlier_pts, axis=0)
        shifted = inlier_pts - center
        _, _, vh = np.linalg.svd(shifted)
        refined_norm = vh[2]
        if refined_norm[2] < 0:
            refined_norm = -refined_norm
        if abs(refined_norm[2]) >= cos_tol:
            best_normal = refined_norm
            best_d = -float(np.dot(best_normal, center))

        center_xy = np.mean(mesh.vertices[:, :2], axis=0)
        z_floor = float(-(best_d + best_normal[0] * center_xy[0] + best_normal[1] * center_xy[1]) / best_normal[2])
        return best_normal, best_d, z_floor

    # -------------------------------------------------------------------------
    # Backward compatibility with Phase 0 scaffold interface
    # -------------------------------------------------------------------------

    def remove_isolated_components(self, mesh_path: Path, output_path: Path, min_faces: int = 100) -> Path:
        """Remove floating disconnected triangle clusters smaller than min_faces."""
        loaded = trimesh.load(mesh_path, process=False)
        if isinstance(loaded, trimesh.Scene):
            loaded = trimesh.util.concatenate(list(loaded.geometry.values()))
        from loom.mesh.components import MeshComponentAnalyzer
        cfg = MeshConfig(component_strategy="min_faces", min_component_faces=min_faces)
        filtered, _ = MeshComponentAnalyzer.filter_components(loaded, cfg)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        filtered.export(output_path)
        return output_path

    def remove_unreferenced_vertices(self, mesh_path: Path, output_path: Path) -> Path:
        """Clean mesh by eliminating unreferenced vertices and zero-area faces."""
        loaded = trimesh.load(mesh_path, process=False)
        if isinstance(loaded, trimesh.Scene):
            loaded = trimesh.util.concatenate(list(loaded.geometry.values()))
        cfg = MeshConfig(remove_unreferenced_vertices=True, remove_degenerate_faces=True)
        cleaned, _ = self.clean(loaded, cfg)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cleaned.export(output_path)
        return output_path


# Module-level convenience aliases conforming to project rules
cull_mesh_by_point_cloud_distance = MeshCleaner.cull_by_point_cloud_distance
fit_floor_plane_ransac = MeshCleaner.fit_floor_plane_ransac

