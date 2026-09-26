"""Tests for metric scaling and calibration interfaces."""

from __future__ import annotations

from pathlib import Path
import pytest
from loom.scaling.aruco import ArucoDetector
from loom.scaling.calibration import ScaleCalibrator
from loom.scaling.transform import ScaleTransformer


def test_scale_calibrator_validation() -> None:
    """Verify ScaleCalibrator rejects non-positive marker dimensions."""
    with pytest.raises(ValueError):
        ScaleCalibrator(marker_size_mm=-10.0)

    calib = ScaleCalibrator(marker_size_mm=50.0)
    assert calib.marker_size_mm == 50.0

    with pytest.raises(NotImplementedError):
        calib.compute_scale_factor([])


def test_scale_transformer_validation() -> None:
    """Verify ScaleTransformer rejects non-positive scale factors."""
    transformer = ScaleTransformer()
    with pytest.raises(ValueError):
        transformer.apply_scale(Path("mesh.obj"), -1.0, Path("out.obj"))

    with pytest.raises(NotImplementedError):
        transformer.apply_scale(Path("mesh.obj"), 1.5, Path("out.obj"))


def test_aruco_detector_raises_not_implemented() -> None:
    """Verify ArucoDetector raises NotImplementedError on scaffolded methods."""
    detector = ArucoDetector()
    with pytest.raises(NotImplementedError):
        detector.detect_in_image(Path("frame.png"))
