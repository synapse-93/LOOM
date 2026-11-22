"""Orchestrator for the Phase 3 raw geometry and mesh processing pipeline."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np
import trimesh

from loom.config.models import MeshConfig
from loom.mesh.cleanup import MeshCleaner
from loom.mesh.components import MeshComponentAnalyzer
from loom.mesh.diagnostics import SUPPORTED_EXTENSIONS, MeshDiagnostics
from loom.mesh.exceptions import (
    MeshError,
    MeshFormatError,
    MeshInvalidError,
    MeshLoadError,
    MeshProcessingError,
)
from loom.mesh.models import CleanupActionResult, MeshProcessingResult, MeshProcessingStage
from loom.mesh.repair import MeshRepairer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SolidificationResult:
    """Result of Taubin polish, watertight solidification, decimation, and metric scaling."""

    mesh: trimesh.Trimesh
    solidification_method: str  # "planar_cap" | "hole_fill" | "voxel_remesh"
    scale_factor: float
    is_watertight: bool
    is_winding_consistent: bool
    is_manifold: bool
    volume_mm3: float
    extents_mm: tuple[float, float, float]
    z_min_mm: float
    validation_passed: bool


class MeshProcessor:
    """Orchestrates sequential geometry diagnostics, component filtering, cleanup, and repair."""

    def __init__(self, config: Optional[MeshConfig] = None) -> None:
        self.config = config or MeshConfig()

    def validate_input(self, mesh_path: Path) -> Path:
        """Validate that input mesh path exists, is a file, and has a supported format."""
        resolved = Path(mesh_path).resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Input mesh does not exist: {mesh_path}")
        if not resolved.is_file():
            raise MeshInvalidError(f"Input mesh path is not a file: {mesh_path}")
        if resolved.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise MeshFormatError(
                f"Unsupported mesh format '{resolved.suffix}'. Supported formats: {sorted(SUPPORTED_EXTENSIONS)}"
            )
        return resolved

    def process(
        self,
        input_mesh_path: Path,
        output_mesh_path: Optional[Path] = None,
        config: Optional[MeshConfig] = None,
        point_cloud_path: Optional[Path | str] = None,
        raise_on_error: bool = True,
    ) -> MeshProcessingResult:
        """Execute the complete Phase 3 mesh processing pipeline.

        Stages:
            1. Input validation & loading
            2. Geometry diagnostics (Before)
            3. Component analysis & filtering
            4. Invalid & degenerate geometry cleanup
            5. Conservative defect repair (hole closure & normal unification)
            6. Mesh normalization (coordinate-preserving)
            7. Geometry diagnostics (After)
            8. Output export & result packaging
        """
        start_time = time.perf_counter()
        active_cfg = config or self.config

        resolved_input: Optional[Path] = None
        if output_mesh_path is not None:
            resolved_output = Path(output_mesh_path).resolve()
        else:
            resolved_output = Path(input_mesh_path).resolve().parent / f"{Path(input_mesh_path).stem}_cleaned.obj"
        warnings: list[str] = []
        stages_completed: list[str] = []

        try:
            # Stage 1: Input validation
            resolved_input = self.validate_input(input_mesh_path)
            logger.info("=== Starting Phase 3: Mesh Processing for '%s' ===", resolved_input.name)

            try:
                loaded = trimesh.load(resolved_input, process=False)
                if isinstance(loaded, trimesh.Scene):
                    if len(loaded.geometry) == 0:
                        raise MeshInvalidError(f"Mesh file contains no geometry: {resolved_input}")
                    mesh = trimesh.util.concatenate(list(loaded.geometry.values()))
                elif isinstance(loaded, trimesh.Trimesh):
                    mesh = loaded
                else:
                    raise MeshLoadError(f"File loaded as unexpected type: {type(loaded)}")

                if resolved_input.suffix.lower() == ".stl":
                    mesh.merge_vertices()
            except (MeshFormatError, MeshInvalidError):
                raise
            except Exception as exc:
                raise MeshLoadError(f"Failed to load mesh '{resolved_input}': {exc}") from exc

            # Verify minimum geometric primitives
            if len(mesh.vertices) < 3 or len(mesh.faces) < 1:
                raise MeshInvalidError(
                    f"Mesh contains insufficient geometry: {len(mesh.vertices)} vertices, {len(mesh.faces)} faces."
                )

            stages_completed.append(MeshProcessingStage.VALIDATE_INPUT.value)

            # Stage 2: Initial Diagnostics
            degen_thresh = getattr(active_cfg, "degenerate_area_threshold", 1e-7)
            diagnostics_before = MeshDiagnostics.inspect(mesh, degenerate_area_threshold=degen_thresh)
            warnings.extend(diagnostics_before.warnings)
            logger.info(
                "Initial diagnostics: %d vertices, %d faces, %d components, %d boundary edges, status=%s",
                diagnostics_before.vertex_count,
                diagnostics_before.face_count,
                diagnostics_before.component_count,
                diagnostics_before.boundary_edge_count,
                diagnostics_before.status,
            )
            stages_completed.append(MeshProcessingStage.DIAGNOSTICS_BEFORE.value)

            # Stage 2b: Point Cloud KDTree Distance Culling (if point cloud provided)
            cull_action: Optional[dict[str, Any]] = None
            resolved_pc = point_cloud_path or getattr(active_cfg, "point_cloud_path", None)
            if resolved_pc is not None and Path(resolved_pc).is_file():
                cull_output_path = resolved_output.parent / "03_distance_culled.ply"
                mult = getattr(active_cfg, "culling_multiplier", 3.5)
                mesh, cull_action = MeshCleaner.cull_by_point_cloud_distance(
                    mesh,
                    point_cloud=resolved_pc,
                    multiplier=mult,
                    output_path=cull_output_path,
                )
                stages_completed.append(MeshProcessingStage.CULL_DISTANCE.value)

            floor_action: Optional[dict[str, Any]] = None
            if active_cfg.floor_removal_enabled and cull_action is None:
                floor_output_path = resolved_output.parent / "04_floor_removed.ply"
                mesh, floor_action = MeshCleaner.remove_floor_plane(
                    mesh,
                    normal_tolerance_deg=active_cfg.floor_normal_tolerance_deg,
                    bottom_percentile=active_cfg.floor_bottom_percentile,
                    distance_threshold=active_cfg.floor_distance_threshold,
                    output_path=floor_output_path,
                )
                stages_completed.append(MeshProcessingStage.REMOVE_FLOOR.value)

            # Stage 3: Connected Component Filtering
            mesh, comp_action = MeshComponentAnalyzer.filter_components(mesh, active_cfg)
            stages_completed.append(MeshProcessingStage.ANALYZE_COMPONENTS.value)

            # Stage 4: Invalid & Degenerate Geometry Cleanup
            if cull_action is None and not active_cfg.turbo:
                mesh, cleanup_action = MeshCleaner.clean(mesh, active_cfg)
            else:
                mesh.remove_unreferenced_vertices()
                cleanup_action = CleanupActionResult(
                    invalid_vertices_removed=0,
                    invalid_faces_removed=0,
                    degenerate_faces_removed=0,
                    duplicate_faces_removed=0,
                    unreferenced_vertices_removed=0,
                    vertices_before=len(mesh.vertices),
                    vertices_after=len(mesh.vertices),
                    faces_before=len(mesh.faces),
                    faces_after=len(mesh.faces),
                )
            stages_completed.append(MeshProcessingStage.CLEAN_INVALID.value)

            # Stage 5: Planar Base Capping (if enabled)
            base_capping_action: Optional[dict[str, Any]] = None
            if active_cfg.base_capping_enabled:
                cap_output_path = resolved_output.parent / "05_base_capped.ply"
                mesh, base_capping_action = MeshRepairer.slice_and_cap_base(
                    mesh,
                    z_base=active_cfg.base_capping_z,
                    bottom_percentile=active_cfg.base_capping_percentile,
                    output_path=cap_output_path,
                )
                stages_completed.append(MeshProcessingStage.BASE_CAPPING.value)

            # Stage 6: Conservative Defect & Hole Repair
            mesh, repair_action = MeshRepairer.repair(mesh, active_cfg)
            stages_completed.append(MeshProcessingStage.REPAIR_DEFECTS.value)

            # Stage 6: Mesh Normalization (preserving coordinates and scale)
            mesh = self._normalize_mesh(mesh)
            stages_completed.append(MeshProcessingStage.NORMALIZE.value)

            # Stage 7: Post-Processing Diagnostics
            diagnostics_after = MeshDiagnostics.inspect(mesh, degenerate_area_threshold=degen_thresh)
            stages_completed.append(MeshProcessingStage.DIAGNOSTICS_AFTER.value)

            # Collect any remaining warnings
            for w in diagnostics_after.warnings:
                if w not in warnings:
                    warnings.append(w)

            # Stage 8: Output Export
            resolved_output.parent.mkdir(parents=True, exist_ok=True)
            mesh.export(resolved_output)
            logger.info("Exported clean intermediate mesh to: %s", resolved_output)
            stages_completed.append(MeshProcessingStage.EXPORT_REPORT.value)

            execution_time = time.perf_counter() - start_time
            overall_status = "WARNING" if len(diagnostics_after.warnings) > 0 else "SUCCESS"


            return MeshProcessingResult(
                success=True,
                input_mesh_path=resolved_input,
                output_mesh_path=resolved_output,
                execution_time_seconds=execution_time,
                diagnostics_before=diagnostics_before,
                diagnostics_after=diagnostics_after,
                components_action=comp_action,
                cleanup_action=cleanup_action,
                repair_action=repair_action,
                floor_action=floor_action,
                cull_action=cull_action,
                base_capping_action=base_capping_action,
                warnings=warnings,
                error_message=None,
                status=overall_status,
                stages_completed=stages_completed,
            )

        except Exception as exc:
            if raise_on_error:
                raise
            execution_time = time.perf_counter() - start_time
            logger.error("Mesh processing failed: %s", exc)
            return MeshProcessingResult(
                success=False,
                input_mesh_path=resolved_input or Path(input_mesh_path),
                output_mesh_path=resolved_output,
                execution_time_seconds=execution_time,
                diagnostics_before=None,
                diagnostics_after=None,
                components_action=None,
                cleanup_action=None,
                repair_action=None,
                warnings=warnings,
                error_message=str(exc),
                status="FAILED",
                stages_completed=stages_completed,
            )


    @staticmethod
    def _normalize_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        """Normalize mesh data structures while strictly preserving coordinate values and scale."""
        # Ensure contiguous arrays with proper data types
        vertices = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
        faces = np.ascontiguousarray(mesh.faces, dtype=np.int64)

        normalized = trimesh.Trimesh(
            vertices=vertices,
            faces=faces,
            process=False,
        )

        # Recompute vertex and face normals if geometry exists
        if len(faces) > 0 and len(vertices) > 0:
            try:
                _ = normalized.vertex_normals
                _ = normalized.face_normals
            except Exception as e:
                logger.debug("Normal calculation notice: %s", e)

        if normalized.is_watertight and getattr(normalized, "volume", None) is not None:
            if normalized.volume < 0:
                normalized.faces = normalized.faces[:, ::-1]

        return normalized

    # ------------------------------------------------------------------
    # Phase 4: Feature-Preserving Polish & Guaranteed Watertight Export
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_largest_component(mesh: trimesh.Trimesh, *, drop_slivers: bool = True) -> trimesh.Trimesh:
        """Merge vertices, optionally drop degenerate/duplicate faces, and keep largest component."""
        m = trimesh.Trimesh(
            vertices=np.ascontiguousarray(mesh.vertices, dtype=np.float64),
            faces=np.ascontiguousarray(mesh.faces, dtype=np.int64),
            process=False,
        )
        if len(m.faces) == 0 or len(m.vertices) == 0:
            return m
        m.merge_vertices()
        # Never strip sliver faces from an already-watertight mesh (would rip open boundary edges)
        if drop_slivers and not m.is_watertight:
            try:
                non_degen = m.nondegenerate_faces()
                if len(non_degen) == len(m.faces) and np.any(non_degen):
                    m.update_faces(non_degen)
            except Exception:
                pass
        try:
            uniq = m.unique_faces()
            if len(uniq) == len(m.faces) and np.any(uniq):
                m.update_faces(uniq)
        except Exception:
            pass
        m.remove_unreferenced_vertices()
        try:
            parts = m.split(only_watertight=False)
            if len(parts) > 1:
                parts.sort(key=lambda p: len(p.faces), reverse=True)
                m = parts[0]
        except Exception:
            pass
        return m

    @staticmethod
    def _orient_positive_volume(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        """Unify face winding/normals and guarantee positive enclosed volume when watertight."""
        import warnings

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            try:
                trimesh.repair.fix_winding(mesh)
            except Exception:
                pass
            try:
                trimesh.repair.fix_normals(mesh)
            except Exception:
                pass
            if mesh.is_watertight:
                try:
                    if float(mesh.volume) < 0.0:
                        mesh.faces = mesh.faces[:, ::-1]
                        trimesh.repair.fix_normals(mesh)
                except Exception:
                    pass
        return mesh

    @staticmethod
    def _trimesh_to_o3d(mesh: trimesh.Trimesh) -> Any:
        import open3d as o3d

        o3d_mesh = o3d.geometry.TriangleMesh()
        o3d_mesh.vertices = o3d.utility.Vector3dVector(np.asarray(mesh.vertices, dtype=np.float64))
        o3d_mesh.triangles = o3d.utility.Vector3iVector(np.asarray(mesh.faces, dtype=np.int32))
        o3d_mesh.compute_vertex_normals()
        return o3d_mesh

    @staticmethod
    def _o3d_to_trimesh(o3d_mesh: Any) -> trimesh.Trimesh:
        verts = np.asarray(o3d_mesh.vertices, dtype=np.float64)
        faces = np.asarray(o3d_mesh.triangles, dtype=np.int64)
        return trimesh.Trimesh(vertices=verts, faces=faces, process=False)

    @classmethod
    def _apply_taubin_smoothing(
        cls,
        mesh: trimesh.Trimesh,
        *,
        iterations: int = 5,
        lambda_filter: float = 0.5,
        mu: float = -0.53,
    ) -> trimesh.Trimesh:
        """Apply feature-preserving Taubin smoothing (zero shrinkage) via Open3D with trimesh fallback."""
        if iterations <= 0 or len(mesh.faces) == 0:
            return mesh.copy()
        try:
            o3d_mesh = cls._trimesh_to_o3d(mesh)
            smoothed = o3d_mesh.filter_smooth_taubin(
                number_of_iterations=int(iterations),
                lambda_filter=float(lambda_filter),
                mu=float(mu),
            )
            smoothed.compute_vertex_normals()
            return cls._o3d_to_trimesh(smoothed)
        except Exception as exc:
            logger.debug("Open3D Taubin smoothing unavailable (%s); falling back to trimesh.", exc)
            try:
                m_copy = mesh.copy()
                trimesh.smoothing.filter_taubin(
                    m_copy, lamb=float(lambda_filter), nu=float(mu), iterations=int(iterations)
                )
                return m_copy
            except Exception:
                return mesh.copy()

    @classmethod
    def _poisson_solidify(
        cls,
        mesh: trimesh.Trimesh,
        *,
        depth: int = 9,
        base_percentile: float = 2.0,
    ) -> trimesh.Trimesh:
        """Tier 2 watertight solidification via Open3D Screened Poisson + optional flat base cap."""
        from loom.printability.gate import PrintabilityGate

        gate = PrintabilityGate()

        try:
            import open3d as o3d

            src = cls._orient_positive_volume(cls._clean_largest_component(mesh))
            o3d_src = cls._trimesh_to_o3d(src)
            o3d_src.compute_triangle_normals()
            o3d_src.compute_vertex_normals()

            # Sample dense oriented surface points for Screened Poisson
            n_samples = min(max(len(src.faces) * 4, 80_000), 220_000)
            pcd = o3d_src.sample_points_uniformly(number_of_points=n_samples)
            pts = np.asarray(pcd.points, dtype=np.float64)
            norms = np.asarray(pcd.normals, dtype=np.float64)

            # Verify outward normal polarity relative to surface centroid
            if len(pts) > 0 and len(norms) == len(pts):
                centroid = np.mean(pts, axis=0)
                radial = pts - centroid[None, :]
                dots = np.sum(radial * norms, axis=1)
                if float(np.median(dots)) < 0.0:
                    norms = -norms
                    pcd.normals = o3d.utility.Vector3dVector(norms)

            p_mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
                pcd, depth=int(depth), scale=1.25, linear_fit=False
            )
            dens_arr = np.asarray(densities, dtype=np.float64)

            # Clean helper on Open3D Poisson output (never strip slivers from a closed surface)
            def _finalize_o3d(candidate_o3d: Any) -> trimesh.Trimesh:
                candidate_o3d.remove_degenerate_triangles()
                candidate_o3d.remove_duplicated_triangles()
                candidate_o3d.remove_duplicated_vertices()
                candidate_o3d.remove_non_manifold_edges()
                tc, cnt, _ = candidate_o3d.cluster_connected_triangles()
                tc_arr = np.asarray(tc)
                cnt_arr = np.asarray(cnt)
                if len(cnt_arr) > 1:
                    largest = int(np.argmax(cnt_arr))
                    candidate_o3d.remove_triangles_by_mask(tc_arr != largest)
                    candidate_o3d.remove_unreferenced_vertices()
                return cls._orient_positive_volume(
                    cls._clean_largest_component(cls._o3d_to_trimesh(candidate_o3d), drop_slivers=False)
                )

            solid = _finalize_o3d(p_mesh)

            # Optional 1% density trim ONLY if watertightness & manifoldness hold strictly
            if len(dens_arr) == len(p_mesh.vertices) and len(dens_arr) > 100:
                try:
                    import copy

                    trimmed_o3d = copy.deepcopy(p_mesh)
                    thresh = float(np.percentile(dens_arr, 1.0))
                    trimmed_o3d.remove_vertices_by_mask(dens_arr < thresh)
                    trimmed = _finalize_o3d(trimmed_o3d)
                    if len(trimmed.faces) > 0 and gate.validate(trimmed).passed:
                        solid = trimmed
                except Exception:
                    pass

            # Re-flatten the bottom base at 2nd percentile Z with mapbox-earcut if gate remains PASS
            if len(solid.vertices) > 0 and gate.validate(solid).passed:
                z_cut = float(np.percentile(solid.vertices[:, 2], base_percentile))
                try:
                    recapped, _ = MeshRepairer.slice_and_cap_base(solid, z_base=z_cut)
                    recapped = cls._orient_positive_volume(
                        cls._clean_largest_component(recapped, drop_slivers=False)
                    )
                    if len(recapped.faces) > 0 and gate.validate(recapped).passed:
                        return recapped
                except Exception as exc:
                    logger.debug("[EXPORT] Post-Poisson base re-flatten skipped: %s", exc)
                return solid
        except Exception as exc:
            logger.warning("[EXPORT] Open3D Screened Poisson solidification failed (%s); using voxel fallback.", exc)

        # High-resolution voxel-remesh + Taubin polish fallback guaranteeing a watertight 2-manifold solid
        pitch = max(float(np.max(mesh.extents)) / 180.0, 1e-4)
        vox = mesh.voxelized(pitch=pitch).fill()
        vox_mesh = cls._orient_positive_volume(
            cls._clean_largest_component(vox.marching_cubes, drop_slivers=False)
        )
        vox_mesh = cls._apply_taubin_smoothing(vox_mesh, iterations=4, lambda_filter=0.5, mu=-0.53)
        vox_mesh = cls._orient_positive_volume(
            cls._clean_largest_component(vox_mesh, drop_slivers=False)
        )
        # Flatten bottom base cleanly via mapbox-earcut if gate remains PASS
        if len(vox_mesh.vertices) > 0:
            z_min_v = float(np.min(vox_mesh.vertices[:, 2]))
            z_max_v = float(np.max(vox_mesh.vertices[:, 2]))
            z_cut_v = max(
                float(np.percentile(vox_mesh.vertices[:, 2], base_percentile)),
                z_min_v + (base_percentile / 100.0) * max(z_max_v - z_min_v, 1e-6),
            )
            try:
                recapped_v, _ = MeshRepairer.slice_and_cap_base(vox_mesh, z_base=z_cut_v)
                recapped_v = cls._orient_positive_volume(
                    cls._clean_largest_component(recapped_v, drop_slivers=False)
                )
                if len(recapped_v.faces) > 0 and gate.validate(recapped_v).passed:
                    return recapped_v
            except Exception as exc:
                logger.debug("[EXPORT] Post-voxel base re-flatten skipped: %s", exc)
        return vox_mesh

    @classmethod
    def _quadric_decimate_if_needed(
        cls,
        mesh: trimesh.Trimesh,
        *,
        max_faces: int = 200_000,
        target_faces: int = 150_000,
    ) -> trimesh.Trimesh:
        """Run Open3D quadric decimation when faces > max_faces, keeping result only if gate passes."""
        if len(mesh.faces) <= int(max_faces):
            return mesh
        from loom.printability.gate import PrintabilityGate

        gate = PrintabilityGate()
        try:
            o3d_mesh = cls._trimesh_to_o3d(mesh)
            dec = o3d_mesh.simplify_quadric_decimation(target_number_of_triangles=int(target_faces))
            dec.remove_degenerate_triangles()
            dec.remove_duplicated_triangles()
            dec.remove_duplicated_vertices()
            dec.remove_non_manifold_edges()
            dec.remove_unreferenced_vertices()
            cand = cls._orient_positive_volume(cls._clean_largest_component(cls._o3d_to_trimesh(dec)))
            if len(cand.faces) > 0 and gate.validate(cand).passed:
                logger.info(
                    "[EXPORT] Quadric decimation preserved watertight manifold: %d -> %d faces",
                    len(mesh.faces),
                    len(cand.faces),
                )
                return cand
            logger.info(
                "[EXPORT] Quadric decimation broke watertightness; keeping full %d-face watertight mesh.",
                len(mesh.faces),
            )
        except Exception as exc:
            logger.debug("[EXPORT] Quadric decimation skipped: %s", exc)
        return mesh

    @classmethod
    def solidify_for_print(
        cls,
        mesh: trimesh.Trimesh,
        *,
        target_length_mm: float = 200.0,
        base_z: Optional[float] = None,
        base_percentile: float = 2.0,
        taubin_iterations: int = 5,
        taubin_lambda: float = 0.5,
        taubin_mu: float = -0.53,
        max_faces_before_decimate: int = 200_000,
        target_decimate_faces: int = 150_000,
        poisson_depth: int = 9,
    ) -> SolidificationResult:
        """Polish, flatten base, guarantee watertight 2-manifold solid, decimate, and scale in float64."""
        from loom.printability.gate import PrintabilityGate

        gate = PrintabilityGate()
        logger.info(
            "[EXPORT] Starting surface polish & watertight solidification (%d verts, %d faces)",
            len(mesh.vertices),
            len(mesh.faces),
        )

        # 1. Clean largest connected component + feature-preserving Taubin smoothing
        cleaned = cls._clean_largest_component(mesh)
        polished = cls._apply_taubin_smoothing(
            cleaned,
            iterations=taubin_iterations,
            lambda_filter=taubin_lambda,
            mu=taubin_mu,
        )
        polished = cls._clean_largest_component(polished)
        logger.info("[EXPORT] Applied Taubin smoothing (%d iters, lambda=%.2f, mu=%.2f)", taubin_iterations, taubin_lambda, taubin_mu)

        # 2. Planar base slice at 2nd percentile Z (at least 2% of Z-span above z_min to avoid rim slivers)
        z_min_p = float(np.min(polished.vertices[:, 2]))
        z_max_p = float(np.max(polished.vertices[:, 2]))
        z_span_p = max(z_max_p - z_min_p, 1e-6)
        if base_z is not None:
            cut_z = float(base_z)
        else:
            p_z = float(np.percentile(polished.vertices[:, 2], base_percentile))
            cut_z = max(p_z, z_min_p + (base_percentile / 100.0) * z_span_p)
        capped, cap_info = MeshRepairer.slice_and_cap_base(polished, z_base=cut_z)
        capped = cls._orient_positive_volume(cls._clean_largest_component(capped, drop_slivers=False))
        logger.info(
            "[EXPORT] Planar base cut & mapbox-earcut cap at Z=%.4f (loops=%d, cap_faces=%d, watertight=%s)",
            cut_z,
            int(cap_info.get("boundary_loops_capped", 0)),
            int(cap_info.get("cap_faces_added", 0)),
            capped.is_watertight,
        )

        solid_mesh: Optional[trimesh.Trimesh] = None
        method = "planar_cap"

        if len(capped.faces) > 0 and gate.validate(capped).passed:
            solid_mesh = capped
            method = "planar_cap"

        # 3. Tier 1: Hole fill + normal/winding repair
        if solid_mesh is None and len(capped.faces) > 0:
            logger.info("[EXPORT] Tier 1 hole repair: closing residual holes & unifying winding...")
            tier1, _ = MeshRepairer.repair(
                capped,
                MeshConfig(close_holes=True, close_all_holes=True, unify_normals=True),
            )
            try:
                trimesh.repair.fill_holes(tier1)
            except Exception:
                pass
            tier1 = cls._orient_positive_volume(cls._clean_largest_component(tier1))
            if len(tier1.faces) > 0 and gate.validate(tier1).passed:
                solid_mesh = tier1
                method = "hole_fill"

        # 4. Tier 2: Guaranteed watertight Screened Poisson / Voxel solidification
        if solid_mesh is None:
            logger.info(
                "[EXPORT] Tier 2 watertight solidification: Open3D Screened Poisson (depth=%d) + base flatten...",
                poisson_depth,
            )
            source_for_poisson = capped if len(capped.faces) >= max(32, len(polished.faces) // 4) else polished
            solid_mesh = cls._poisson_solidify(
                source_for_poisson,
                depth=poisson_depth,
                base_percentile=base_percentile,
            )
            method = "voxel_remesh"

        # 5. Quadric decimation when > 200k faces (kept only if watertight & manifold hold)
        solid_mesh = cls._quadric_decimate_if_needed(
            solid_mesh,
            max_faces=max_faces_before_decimate,
            target_faces=target_decimate_faces,
        )

        # 6. Uniform float64 scaling to target_length_mm, Z_min = 0.000 mm, X/Y centered at (0, 0)
        solid_mesh = trimesh.Trimesh(
            vertices=np.ascontiguousarray(solid_mesh.vertices, dtype=np.float64),
            faces=np.ascontiguousarray(solid_mesh.faces, dtype=np.int64),
            process=False,
        )
        max_extent = float(np.max(solid_mesh.extents)) if len(solid_mesh.extents) > 0 else 0.0
        scale_factor = 1.0
        if target_length_mm is not None and float(target_length_mm) > 0.0 and max_extent > 1e-8:
            scale_factor = float(target_length_mm) / max_extent
            solid_mesh.vertices = solid_mesh.vertices * scale_factor

        solid_mesh = cls._orient_positive_volume(solid_mesh)
        z_min_before = float(solid_mesh.bounds[0][2])
        solid_mesh.vertices[:, 2] -= z_min_before
        xy_mid = 0.5 * (solid_mesh.bounds[0, :2] + solid_mesh.bounds[1, :2])
        solid_mesh.vertices[:, 0] -= float(xy_mid[0])
        solid_mesh.vertices[:, 1] -= float(xy_mid[1])

        val = gate.validate(solid_mesh)
        extents_mm = (
            float(solid_mesh.extents[0]),
            float(solid_mesh.extents[1]),
            float(solid_mesh.extents[2]),
        )
        z_min_mm = float(solid_mesh.bounds[0][2])
        logger.info(
            "[EXPORT] PrintabilityGate %s | method=%s | verts=%d faces=%d | watertight=%s manifold=%s "
            "vol=%.2f cm^3 | extents=[%.2f, %.2f, %.2f] mm | Z_min=%.6f mm",
            "PASSED" if val.passed else "FAILED",
            method,
            len(solid_mesh.vertices),
            len(solid_mesh.faces),
            val.is_watertight,
            val.is_manifold,
            val.volume_mm3 / 1000.0,
            extents_mm[0],
            extents_mm[1],
            extents_mm[2],
            z_min_mm,
        )
        return SolidificationResult(
            mesh=solid_mesh,
            solidification_method=method,
            scale_factor=scale_factor,
            is_watertight=val.is_watertight,
            is_winding_consistent=bool(solid_mesh.is_winding_consistent),
            is_manifold=val.is_manifold,
            volume_mm3=val.volume_mm3,
            extents_mm=extents_mm,
            z_min_mm=z_min_mm,
            validation_passed=val.passed,
        )
