"""Domain exceptions for metric scaling and reference marker calibration."""

from __future__ import annotations


class ScalingError(Exception):
    """Base exception for all metric scaling errors."""


class ScalingConfigError(ScalingError, ValueError):
    """Raised when scaling configuration parameters are invalid or unsupported."""


class ReferenceDetectionError(ScalingError):
    """Raised when fiducial reference detection fails or encounters corrupt input."""


class ReferenceMeasurementError(ScalingError, ValueError):
    """Raised when reference measurements are invalid, missing, or physically impossible."""


class ScaleEstimationError(ScalingError, ValueError):
    """Raised when scale factor calculation fails, is non-positive, or non-finite."""


class MeshScalingError(ScalingError):
    """Raised when applying scaling transformation to 3D mesh fails."""


class MeshScalingValidationError(ScalingError):
    """Raised when post-scaling mesh geometry validation fails."""
