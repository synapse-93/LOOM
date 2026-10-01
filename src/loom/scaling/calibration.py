"""Scale recovery calibration from reference fiducials."""

from __future__ import annotations

import math
from typing import Any, Sequence

from loom.scaling.measurement import ScaleEstimator
from loom.scaling.models import MarkerObservation, ReferenceMeasurement


class ScaleCalibrator:
    """Computes physical scale factor from known reference marker dimensions."""

    def __init__(self, marker_size_mm: float = 50.0) -> None:
        """Initialize calibrator with known ground truth reference size."""
        if not math.isfinite(marker_size_mm) or marker_size_mm <= 0.0:
            raise ValueError(f"Marker size must be positive and finite, got {marker_size_mm}")
        self.marker_size_mm = float(marker_size_mm)

    def compute_scale_factor(
        self,
        measurements: Sequence[float | ReferenceMeasurement | MarkerObservation | Any],
    ) -> float:
        """Compute metric scaling scalar (physical_mm / reconstructed_unit).

        Args:
            measurements: Sequence of scalar reconstructed edge lengths, ReferenceMeasurement, or marker observations.

        Returns:
            Scale factor float multiplier.

        Raises:
            ValueError: If measurements sequence is empty or invalid.
        """
        if not measurements or len(measurements) == 0:
            raise ValueError("No measurements provided to compute scale factor.")

        first = measurements[0]
        if isinstance(first, ReferenceMeasurement):
            est = ScaleEstimator.estimate(self.marker_size_mm, first)
            return est.scale_factor
        elif isinstance(first, (int, float)):
            vals = [float(x) for x in measurements]
            mean_recon = sum(vals) / len(vals)
            est = ScaleEstimator.estimate(self.marker_size_mm, mean_recon)
            return est.scale_factor
        elif hasattr(first, "edge_lengths_2d") and getattr(first, "edge_lengths_2d", None):
            edges: list[float] = []
            for m in measurements:
                if hasattr(m, "edge_lengths_2d") and m.edge_lengths_2d:
                    edges.extend(m.edge_lengths_2d)
            if not edges:
                raise ValueError("No edge measurements extracted from detections.")
            mean_edge = sum(edges) / len(edges)
            est = ScaleEstimator.estimate(self.marker_size_mm, mean_edge)
            return est.scale_factor
        else:
            raise ValueError(f"Unsupported measurement type in compute_scale_factor: {type(first)}")
