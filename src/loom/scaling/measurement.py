"""Reference measurement engine and scale estimation for Phase 4 metric scaling."""

from __future__ import annotations

import math
from typing import Sequence
import numpy as np

from loom.scaling.exceptions import (
    ReferenceMeasurementError,
    ScaleEstimationError,
)
from loom.scaling.models import ReferenceMeasurement, ScaleEstimate
from loom.utils.logging import get_logger

logger = get_logger("loom.scaling.measurement")


class MeasurementEngine:
    """Computes robust statistical measurements of physical reference markers in reconstructed coordinates."""

    @staticmethod
    def from_observations(
        observations: Sequence[float],
        units: str = "reconstructed_units",
    ) -> ReferenceMeasurement:
        """Construct aggregated ReferenceMeasurement from a sequence of measured scalar distances.

        Args:
            observations: Sequence of measured lengths/distances.
            units: Unit label for tracking.

        Returns:
            Populated ReferenceMeasurement with mean, median, std_dev, and spread.

        Raises:
            ReferenceMeasurementError: If observations are empty, non-finite, zero, or negative.
        """
        if not observations or len(observations) == 0:
            raise ReferenceMeasurementError("No measurements provided to compute reference size.")

        valid_vals: list[float] = []
        for i, val in enumerate(observations):
            try:
                fval = float(val)
            except (TypeError, ValueError) as exc:
                raise ReferenceMeasurementError(f"Measurement at index {i} is not numeric: {val}") from exc

            if not math.isfinite(fval):
                raise ReferenceMeasurementError(f"Measurement at index {i} is non-finite: {fval}")
            if fval <= 0.0:
                raise ReferenceMeasurementError(
                    f"Measurement at index {i} must be strictly positive (> 0.0), got {fval}"
                )
            valid_vals.append(fval)

        arr = np.array(valid_vals, dtype=np.float64)
        mean_val = float(np.mean(arr))
        median_val = float(np.median(arr))
        std_val = float(np.std(arr)) if len(arr) > 1 else 0.0
        min_val = float(np.min(arr))
        max_val = float(np.max(arr))
        spread_val = max_val - min_val

        # Using median as robust representative reconstructed size
        return ReferenceMeasurement(
            reconstructed_size=median_val,
            observations=valid_vals,
            mean=mean_val,
            median=median_val,
            std_dev=std_val,
            min_val=min_val,
            max_val=max_val,
            spread=spread_val,
            measurement_count=len(valid_vals),
            units=units,
        )

    @staticmethod
    def from_3d_corners(
        corners_3d: Sequence[tuple[float, float, float] | Sequence[float] | np.ndarray],
        units: str = "reconstructed_units",
    ) -> ReferenceMeasurement:
        """Compute four perimeter edge distances from ordered 3D square marker corners.

        Expected order:
            corner 0 -> corner 1 -> corner 2 -> corner 3 (counter-clockwise or clockwise).

        Perimeter edge distances:
            d(c0, c1), d(c1, c2), d(c2, c3), d(c3, c0).
        """
        if len(corners_3d) != 4:
            raise ReferenceMeasurementError(
                f"Expected exactly 4 corner points for 3D marker measurement, got {len(corners_3d)}"
            )

        pts: list[np.ndarray] = []
        for i, c in enumerate(corners_3d):
            arr = np.asarray(c, dtype=np.float64)
            if arr.shape != (3,):
                raise ReferenceMeasurementError(f"Corner {i} must be 3D point (x, y, z), got shape {arr.shape}")
            if not np.all(np.isfinite(arr)):
                raise ReferenceMeasurementError(f"Corner {i} contains NaN or Inf coordinates: {arr}")
            pts.append(arr)

        # 4 perimeter edges
        e01 = float(np.linalg.norm(pts[1] - pts[0]))
        e12 = float(np.linalg.norm(pts[2] - pts[1]))
        e23 = float(np.linalg.norm(pts[3] - pts[2]))
        e30 = float(np.linalg.norm(pts[0] - pts[3]))

        return MeasurementEngine.from_observations([e01, e12, e23, e30], units=units)


class ScaleEstimator:
    """Calculates deterministic metric scale factor relating reconstructed reference to physical truth."""

    @staticmethod
    def estimate(
        known_physical_size_mm: float,
        measurement: ReferenceMeasurement | float,
    ) -> ScaleEstimate:
        """Estimate metric scale factor from known physical dimension and measured reference size.

        scale_factor = known_physical_size_mm / reconstructed_reference_size

        Args:
            known_physical_size_mm: Ground-truth reference marker dimension in millimeters.
            measurement: Either ReferenceMeasurement or a scalar reconstructed distance.

        Returns:
            ScaleEstimate containing scale_factor and variance metrics.

        Raises:
            ScaleEstimationError: If known_physical_size_mm or reconstructed_size is <= 0 or non-finite.
        """
        try:
            physical_mm = float(known_physical_size_mm)
        except (TypeError, ValueError) as exc:
            raise ScaleEstimationError(f"Invalid known physical size: {known_physical_size_mm}") from exc

        if not math.isfinite(physical_mm) or physical_mm <= 0.0:
            raise ScaleEstimationError(
                f"Known physical size must be finite and strictly positive (> 0.0), got {physical_mm}"
            )

        if isinstance(measurement, ReferenceMeasurement):
            recon_size = measurement.reconstructed_size
            variance = float(measurement.std_dev ** 2)
            # Mathematical confidence derived from relative spread: 1.0 - (std_dev / mean)
            if measurement.mean > 0.0:
                rel_spread = measurement.std_dev / measurement.mean
                confidence = max(0.0, min(1.0, 1.0 - rel_spread))
            else:
                confidence = 0.0
        else:
            try:
                recon_size = float(measurement)
            except (TypeError, ValueError) as exc:
                raise ScaleEstimationError(f"Invalid measurement scalar: {measurement}") from exc
            variance = 0.0
            confidence = 1.0

        if not math.isfinite(recon_size) or recon_size <= 0.0:
            raise ScaleEstimationError(
                f"Reconstructed reference size must be finite and strictly positive (> 0.0), got {recon_size}"
            )

        scale_factor = physical_mm / recon_size

        if not math.isfinite(scale_factor) or scale_factor <= 0.0:
            raise ScaleEstimationError(f"Calculated scale factor is non-positive or non-finite: {scale_factor}")

        return ScaleEstimate(
            known_physical_size_mm=physical_mm,
            reconstructed_reference_size=recon_size,
            scale_factor=scale_factor,
            variance=variance,
            confidence=confidence,
            method="ratio",
        )
