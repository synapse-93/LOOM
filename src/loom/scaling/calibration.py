"""Scale recovery calibration from reference fiducials."""

from __future__ import annotations

from typing import Sequence
from loom.scaling.aruco import MarkerDetection


class ScaleCalibrator:
    """Computes physical scale factor from known reference marker dimensions."""

    def __init__(self, marker_size_mm: float = 50.0) -> None:
        if marker_size_mm <= 0.0:
            raise ValueError(f"Marker size must be positive, got {marker_size_mm}")
        self.marker_size_mm = marker_size_mm

    def compute_scale_factor(self, detections: Sequence[MarkerDetection]) -> float:
        """Compute metric scaling scalar (physical_mm / reconstructed_unit).

        Raises:
            NotImplementedError: Scheduled for Phase 4.
        """
        raise NotImplementedError("Scale factor calibration scheduled for Phase 4.")
