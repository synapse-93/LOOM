"""Orchestrator for the Phase 3 raw geometry and mesh processing pipeline."""

from __future__ import annotations

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
