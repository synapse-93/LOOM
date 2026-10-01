"""Unit tests for ArUco detector and dictionary resolution."""

from __future__ import annotations

from pathlib import Path
import cv2
import numpy as np
import pytest

from loom.scaling.aruco import (
    ARUCO_DICTIONARY_MAP,
    ArucoDetector,
    resolve_aruco_dictionary,
)
from loom.scaling.exceptions import ReferenceDetectionError, ScalingConfigError


def test_dictionary_resolution() -> None:
    """Verify dictionary resolution resolves standard names and rejects invalid names."""
    dict_id = resolve_aruco_dictionary("DICT_4X4_50")
    assert dict_id == cv2.aruco.DICT_4X4_50

    dict_id_case = resolve_aruco_dictionary("dict_6x6_250")
    assert dict_id_case == cv2.aruco.DICT_6X6_250

    with pytest.raises(ScalingConfigError):
        resolve_aruco_dictionary("NON_EXISTENT_DICT")


def test_detector_configuration_validation() -> None:
    """Verify ArucoDetector rejects non-positive known sizes."""
    with pytest.raises(ScalingConfigError):
        ArucoDetector(known_size_mm=-5.0)

    with pytest.raises(ScalingConfigError):
        ArucoDetector(known_size_mm=0.0)

    with pytest.raises(ScalingConfigError):
        ArucoDetector(dictionary_name="INVALID_DICT")


def test_synthetic_marker_generation_and_detection(tmp_path: Path) -> None:
    """Verify generating a synthetic marker image and detecting it returns 4 corners and ID."""
    detector = ArucoDetector(dictionary_name="DICT_4X4_50", target_marker_id=0, known_size_mm=50.0)
    marker_img = ArucoDetector.generate_marker_image("DICT_4X4_50", marker_id=0, size_px=200, margin_px=40)

    img_path = tmp_path / "test_marker_0.png"
    cv2.imwrite(str(img_path), marker_img)

    observations = detector.detect_in_image(img_path)
    assert len(observations) == 1

    obs = observations[0]
    assert obs.marker_id == 0
    assert obs.is_valid is True
    assert len(obs.corners_2d) == 4
    assert obs.edge_lengths_2d is not None
    assert len(obs.edge_lengths_2d) == 4
    # With size 200px and 40px border, corners should be around ~199px apart
    for edge in obs.edge_lengths_2d:
        assert edge == pytest.approx(199.0, abs=3.0)


def test_target_marker_id_filtering(tmp_path: Path) -> None:
    """Verify that detector filters for target_id and ignores other IDs."""
    detector = ArucoDetector(dictionary_name="DICT_4X4_50", target_marker_id=4, known_size_mm=50.0)
    # Generate marker 0
    marker_img = ArucoDetector.generate_marker_image("DICT_4X4_50", marker_id=0, size_px=200, margin_px=40)
    img_path = tmp_path / "marker_0.png"
    cv2.imwrite(str(img_path), marker_img)

    # Should find 0 observations matching target_id=4
    obs = detector.detect_in_image(img_path)
    assert len(obs) == 0

    # Overriding target_id to 0 should find it
    obs_override = detector.detect_in_image(img_path, target_id=0)
    assert len(obs_override) == 1
    assert obs_override[0].marker_id == 0


def test_empty_or_corrupt_image(tmp_path: Path) -> None:
    """Verify handling of invalid or unreadable image files."""
    detector = ArucoDetector()
    corrupt_file = tmp_path / "corrupt.png"
    corrupt_file.write_bytes(b"not an image file")

    with pytest.raises(ReferenceDetectionError):
        detector.detect_in_image(corrupt_file)

    blank_img = np.ones((100, 100, 3), dtype=np.uint8) * 255
    obs_blank = detector.detect_in_array(blank_img)
    assert len(obs_blank) == 0
