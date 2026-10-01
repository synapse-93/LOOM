"""Orchestrator for the Phase 3 raw geometry and mesh processing pipeline."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

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
from loom.mesh.models import MeshProcessingResult, MeshProcessingStage

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

            # Stage 3: Connected Component Filtering
            mesh, comp_action = MeshComponentAnalyzer.filter_components(mesh, active_cfg)
            stages_completed.append(MeshProcessingStage.ANALYZE_COMPONENTS.value)

            # Stage 4: Invalid & Degenerate Geometry Cleanup
            mesh, cleanup_action = MeshCleaner.clean(mesh, active_cfg)
            stages_completed.append(MeshProcessingStage.CLEAN_INVALID.value)

            # Stage 5: Conservative Defect & Hole Repair
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


        return normalized
