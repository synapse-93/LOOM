"""Phase 4 scaling pipeline orchestrator."""

from __future__ import annotations

import math
from pathlib import Path
import time
from typing import Optional, Sequence
import numpy as np
import trimesh

from loom.config.models import ScalingConfig
from loom.scaling.aruco import ArucoDetector
from loom.scaling.exceptions import (
    MeshScalingError,
    MeshScalingValidationError,
    ReferenceMeasurementError,
    ScaleEstimationError,
    ScalingConfigError,
    ScalingError,
)
from loom.scaling.measurement import MeasurementEngine, ScaleEstimator
from loom.scaling.models import (
    ReferenceMarker,
    ReferenceMeasurement,
    ScaleEstimate,
    ScalingResult,
)
from loom.scaling.transform import ScaleTransformer
from loom.utils.logging import get_logger

logger = get_logger("loom.scaling.processor")

SUPPORTED_EXTENSIONS = {".obj", ".ply", ".stl"}


class ScalingProcessor:
    """Orchestrates Phase 4 metric scaling of cleaned 3D meshes using physical reference markers."""

    def __init__(self, config: Optional[ScalingConfig] = None) -> None:
        """Initialize scaling processor with configuration."""
        self.config = config or ScalingConfig()
        self._transformer = ScaleTransformer()

    def _validate_mesh_path(self, mesh_path: Path | str) -> Path:
        """Validate input mesh file existence and extension."""
        path = Path(mesh_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Input mesh file does not exist: {path}")
        if not path.is_file():
            raise MeshScalingError(f"Input mesh path is not a file: {path}")
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise MeshScalingError(
                f"Unsupported mesh format '{path.suffix}'. Supported formats: {sorted(SUPPORTED_EXTENSIONS)}"
            )
        return path

    def process(
        self,
        input_mesh_path: Path | str,
        output_mesh_path: Optional[Path | str] = None,
        reference_measurements: Optional[float | Sequence[float] | Sequence[tuple[float, float, float] | Sequence[float] | np.ndarray]] = None,
        reference_marker: Optional[ReferenceMarker] = None,
        origin: Optional[tuple[float, float, float]] = None,
        raise_on_error: bool = True,
    ) -> ScalingResult:
        """Execute Phase 4 metric scaling on input mesh.

        Stages:
            1. Validate input mesh file and configuration.
            2. Acquire and aggregate reference measurements.
            3. Estimate metric scale factor.
            4. Transform mesh coordinates about specified origin.
            5. Validate transformed output mesh geometry.
            6. Export scaled mesh and produce scaling report.

        Args:
            input_mesh_path: Path to cleaned 3D mesh.
            output_mesh_path: Destination path for scaled mesh.
            reference_measurements: Measured size, list of lengths, or 4 3D corners of the reference marker.
            reference_marker: Optional reference marker specification (overrides config).
            origin: Transformation origin (default: config.transformation_origin or (0, 0, 0)).
            raise_on_error: If True, raise typed ScalingError on failure; if False, return failed ScalingResult.

        Returns:
            Populated ScalingResult with measurements, scale factors, and bounding boxes.
        """
        start_time = time.perf_counter()
        warnings: list[str] = []
        errors: list[str] = []

        # Determine reference marker configuration
        marker = reference_marker or ReferenceMarker(
            marker_type=self.config.strategy,
            marker_id=self.config.marker_id,
            known_size_mm=self.config.marker_size_mm,
            dictionary=self.config.dictionary,
        )

        transform_origin = origin or self.config.transformation_origin

        input_str = str(input_mesh_path)
        resolved_output: Optional[Path] = None
        if output_mesh_path is not None:
            resolved_output = Path(output_mesh_path).resolve()
        else:
            in_path = Path(input_mesh_path)
            resolved_output = in_path.resolve().parent / f"{in_path.stem}_scaled.obj"

        try:
            # Stage 1: Validate input mesh
            resolved_input = self._validate_mesh_path(input_mesh_path)

            try:
                loaded = trimesh.load(resolved_input, process=False)
                if isinstance(loaded, trimesh.Scene):
                    if len(loaded.geometry) == 0:
                        raise MeshScalingError("Loaded mesh scene contains no geometry.")
                    mesh = trimesh.util.concatenate(list(loaded.geometry.values()))
                else:
                    mesh = loaded
            except Exception as exc:
                raise MeshScalingError(f"Failed to read mesh file: {exc}") from exc

            v_count_before = len(mesh.vertices)
            f_count_before = len(mesh.faces)
            if v_count_before == 0:
                raise MeshScalingError("Input mesh has 0 vertices.")
            bounds_before = [mesh.bounds[0].tolist(), mesh.bounds[1].tolist()]

            # Stage 2: Validate marker configuration
            if marker.known_size_mm <= 0.0 or not math.isfinite(marker.known_size_mm):
                raise ScalingConfigError(
                    f"Known reference marker size must be strictly positive and finite, got {marker.known_size_mm}"
                )

            # Stage 3: Acquire and aggregate reference measurement
            if reference_measurements is None:
                raise ReferenceMeasurementError(
                    "No reference measurements provided. Live 3D reference extraction requires photogrammetric output."
                )

            measurement: ReferenceMeasurement
            if isinstance(reference_measurements, (int, float)):
                measurement = MeasurementEngine.from_observations([float(reference_measurements)])
            elif isinstance(reference_measurements, Sequence):
                if len(reference_measurements) == 0:
                    raise ReferenceMeasurementError("Reference measurements sequence is empty.")
                first_elem = reference_measurements[0]
                if isinstance(first_elem, (int, float, np.floating, np.integer)):
                    # Scalar observation list
                    measurement = MeasurementEngine.from_observations([float(x) for x in reference_measurements])
                elif isinstance(first_elem, (list, tuple, np.ndarray)) and len(first_elem) == 3:
                    # 4 3D corner coordinates
                    measurement = MeasurementEngine.from_3d_corners(reference_measurements)  # type: ignore
                else:
                    raise ReferenceMeasurementError(
                        f"Unsupported reference measurement format with element type {type(first_elem)}"
                    )
            else:
                raise ReferenceMeasurementError(
                    f"Unsupported reference measurements type: {type(reference_measurements)}"
                )

            # Stage 4: Estimate scale
            scale_est = ScaleEstimator.estimate(marker.known_size_mm, measurement)
            scale_factor = scale_est.scale_factor

            # Stage 5: Transform mesh
            scaled_mesh = self._transformer.transform_mesh(mesh, scale_factor, origin=transform_origin)

            # Stage 6: Validate output mesh
            v_count_after = len(scaled_mesh.vertices)
            f_count_after = len(scaled_mesh.faces)
            if v_count_after != v_count_before or f_count_after != f_count_before:
                raise MeshScalingValidationError(
                    f"Topology corruption: vertex count changed from {v_count_before} to {v_count_after} "
                    f"or face count changed from {f_count_before} to {f_count_after}."
                )
            if not np.all(np.isfinite(scaled_mesh.vertices)):
                raise MeshScalingValidationError("Scaled vertices contain NaN or Inf coordinates.")

            bounds_after = [scaled_mesh.bounds[0].tolist(), scaled_mesh.bounds[1].tolist()]

            # Stage 7: Export scaled mesh
            resolved_output.parent.mkdir(parents=True, exist_ok=True)
            scaled_mesh.export(str(resolved_output))

            exec_time = time.perf_counter() - start_time
            logger.info(
                "Metric scaling succeeded: %s -> %s (factor=%.6f, time=%.4fs)",
                resolved_input.name,
                resolved_output.name,
                scale_factor,
                exec_time,
            )

            return ScalingResult(
                input_mesh_path=str(resolved_input),
                output_mesh_path=str(resolved_output),
                status="SUCCESS",
                reference=marker.to_dict(),
                measurement=measurement.to_dict(),
                scale_estimate=scale_est.to_dict(),
                scale_factor=scale_factor,
                transformation_origin=transform_origin,
                bounds_before=bounds_before,
                bounds_after=bounds_after,
                vertex_count_before=v_count_before,
                vertex_count_after=v_count_after,
                face_count_before=f_count_before,
                face_count_after=f_count_after,
                execution_time_seconds=exec_time,
                warnings=warnings,
                errors=errors,
            )

        except Exception as exc:
            exec_time = time.perf_counter() - start_time
            err_msg = str(exc)
            errors.append(err_msg)
            logger.error("Metric scaling failed for '%s': %s", input_mesh_path, exc)

            status = "FAILED"
            if isinstance(exc, (ReferenceMeasurementError, ScalingConfigError)):
                status = "INVALID_REFERENCE"

            result = ScalingResult(
                input_mesh_path=input_str,
                output_mesh_path=str(resolved_output) if resolved_output else None,
                status=status,
                reference=marker.to_dict() if marker else None,
                measurement=None,
                scale_estimate=None,
                scale_factor=1.0,
                transformation_origin=transform_origin,
                bounds_before=None,
                bounds_after=None,
                vertex_count_before=0,
                vertex_count_after=0,
                face_count_before=0,
                face_count_after=0,
                execution_time_seconds=exec_time,
                warnings=warnings,
                errors=errors,
            )

            if raise_on_error:
                raise
            return result
