"""Metric scaling and reference marker calibration module for LOOM."""

from __future__ import annotations

from loom.scaling.aruco import ArucoDetector, ARUCO_DICTIONARY_MAP, resolve_aruco_dictionary
from loom.scaling.calibration import ScaleCalibrator
from loom.scaling.exceptions import (
    MeshScalingError,
    MeshScalingValidationError,
    ReferenceDetectionError,
    ReferenceMeasurementError,
    ScaleEstimationError,
    ScalingConfigError,
    ScalingError,
)
from loom.scaling.measurement import MeasurementEngine, ScaleEstimator
from loom.scaling.models import (
    MarkerObservation,
    ReferenceMarker,
    ReferenceMeasurement,
    ScaleEstimate,
    ScalingResult,
)
from loom.scaling.processor import ScalingProcessor
from loom.scaling.transform import ScaleTransformer

# Backward-compatible alias
MarkerDetection = MarkerObservation

__all__ = [
    "ArucoDetector",
    "ARUCO_DICTIONARY_MAP",
    "resolve_aruco_dictionary",
    "MarkerDetection",
    "MarkerObservation",
    "ReferenceMarker",
    "ReferenceMeasurement",
    "ScaleCalibrator",
    "ScaleEstimate",
    "ScaleEstimator",
    "ScaleTransformer",
    "MeasurementEngine",
    "ScalingProcessor",
    "ScalingResult",
    "ScalingError",
    "ScalingConfigError",
    "ReferenceDetectionError",
    "ReferenceMeasurementError",
    "ScaleEstimationError",
    "MeshScalingError",
    "MeshScalingValidationError",
]
