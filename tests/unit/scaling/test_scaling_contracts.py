"""Tests for metric scaling and calibration interfaces."""

from __future__ import annotations

from pathlib import Path
import pytest
from loom.scaling.aruco import ArucoDetector
from loom.scaling.calibration import ScaleCalibrator
from loom.scaling.transform import ScaleTransformer


def test_scale_calibrator_validation() -> None:
    """Verify ScaleCalibrator validates marker dimensions and computes scale."""
    with pytest.raises(ValueError):
        ScaleCalibrator(marker_size_mm=-10.0)

    with pytest.raises(ValueError):
        ScaleCalibrator(marker_size_mm=0.0)

    calib = ScaleCalibrator(marker_size_mm=50.0)
    assert calib.marker_size_mm == 50.0

    # Rejects empty observations
    with pytest.raises(ValueError):
        calib.compute_scale_factor([])

    # Computes valid scale factor
    factor = calib.compute_scale_factor([25.0])
    assert factor == pytest.approx(2.0)


def test_scale_transformer_validation(tmp_path: Path) -> None:
    """Verify ScaleTransformer validates scale factors and handles files."""
    transformer = ScaleTransformer()
    with pytest.raises(ValueError):
        transformer.apply_scale(Path("mesh.obj"), -1.0, Path("out.obj"))

    with pytest.raises(ValueError):
        transformer.apply_scale(Path("mesh.obj"), 0.0, Path("out.obj"))

    # Non-existent file raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        transformer.apply_scale(Path("non_existent_mesh.obj"), 1.5, tmp_path / "out.obj")


def test_aruco_detector_file_handling() -> None:
    """Verify ArucoDetector raises FileNotFoundError when image does not exist."""
    detector = ArucoDetector()
    with pytest.raises(FileNotFoundError):
        detector.detect_in_image(Path("non_existent_frame.png"))
