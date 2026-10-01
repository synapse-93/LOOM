"""ArUco fiducial marker detection interfaces and OpenCV implementation."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional, Sequence
import cv2
import numpy as np

from loom.scaling.exceptions import (
    ReferenceDetectionError,
    ScalingConfigError,
)
from loom.scaling.models import MarkerObservation, ReferenceMarker
from loom.utils.logging import get_logger

logger = get_logger("loom.scaling.aruco")

ARUCO_DICTIONARY_MAP: dict[str, int] = {
    "DICT_4X4_50": cv2.aruco.DICT_4X4_50,
    "DICT_4X4_100": cv2.aruco.DICT_4X4_100,
    "DICT_4X4_250": cv2.aruco.DICT_4X4_250,
    "DICT_4X4_1000": cv2.aruco.DICT_4X4_1000,
    "DICT_5X5_50": cv2.aruco.DICT_5X5_50,
    "DICT_5X5_100": cv2.aruco.DICT_5X5_100,
    "DICT_5X5_250": cv2.aruco.DICT_5X5_250,
    "DICT_5X5_1000": cv2.aruco.DICT_5X5_1000,
    "DICT_6X6_50": cv2.aruco.DICT_6X6_50,
    "DICT_6X6_100": cv2.aruco.DICT_6X6_100,
    "DICT_6X6_250": cv2.aruco.DICT_6X6_250,
    "DICT_6X6_1000": cv2.aruco.DICT_6X6_1000,
    "DICT_7X7_50": cv2.aruco.DICT_7X7_50,
    "DICT_7X7_100": cv2.aruco.DICT_7X7_100,
    "DICT_7X7_250": cv2.aruco.DICT_7X7_250,
    "DICT_7X7_1000": cv2.aruco.DICT_7X7_1000,
    "DICT_ARUCO_ORIGINAL": cv2.aruco.DICT_ARUCO_ORIGINAL,
}


def resolve_aruco_dictionary(dictionary_name: str) -> int:
    """Resolve dictionary name string to OpenCV constant."""
    name_upper = dictionary_name.strip().upper()
    if name_upper not in ARUCO_DICTIONARY_MAP:
        supported = ", ".join(sorted(ARUCO_DICTIONARY_MAP.keys()))
        raise ScalingConfigError(
            f"Unsupported ArUco dictionary '{dictionary_name}'. Supported options: {supported}"
        )
    return ARUCO_DICTIONARY_MAP[name_upper]


class ArucoDetector:
    """Detects ArUco fiducial markers in captured video keyframes."""

    def __init__(
        self,
        dictionary_name: str = "DICT_4X4_50",
        target_marker_id: Optional[int] = None,
        known_size_mm: float = 50.0,
    ) -> None:
        """Initialize ArUco detector with dictionary and target parameters."""
        self.dictionary_name = dictionary_name
        self.dict_id = resolve_aruco_dictionary(dictionary_name)
        self.target_marker_id = target_marker_id
        if known_size_mm <= 0.0 or not math.isfinite(known_size_mm):
            raise ScalingConfigError(f"Known marker size must be positive and finite, got {known_size_mm}")
        self.known_size_mm = float(known_size_mm)

        self._dictionary = cv2.aruco.getPredefinedDictionary(self.dict_id)
        self._parameters = cv2.aruco.DetectorParameters()
        self._detector = cv2.aruco.ArucoDetector(self._dictionary, self._parameters)

    @property
    def reference_marker(self) -> ReferenceMarker:
        """Construct reference marker specification model."""
        return ReferenceMarker(
            marker_type="aruco",
            marker_id=self.target_marker_id if self.target_marker_id is not None else 0,
            known_size_mm=self.known_size_mm,
            dictionary=self.dictionary_name,
        )

    def detect_in_image(
        self,
        image_path: Path | str,
        target_id: Optional[int] = None,
    ) -> list[MarkerObservation]:
        """Detect markers in a single image file.

        Args:
            image_path: Path to image file on disk.
            target_id: Optional explicit marker ID to filter by. Defaults to self.target_marker_id.

        Returns:
            List of MarkerObservation objects for valid detections matching target_id.

        Raises:
            FileNotFoundError: If image file does not exist.
            ReferenceDetectionError: If image file cannot be decoded.
        """
        path = Path(image_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Image file does not exist: {path}")

        image = cv2.imread(str(path))
        if image is None:
            raise ReferenceDetectionError(f"Failed to read or decode image at: {path}")

        return self.detect_in_array(image, frame_path=str(path), target_id=target_id)

    def detect_in_array(
        self,
        image: np.ndarray,
        frame_path: Optional[str] = None,
        target_id: Optional[int] = None,
    ) -> list[MarkerObservation]:
        """Detect markers in an in-memory numpy BGR or Grayscale image array."""
        if image is None or image.size == 0:
            raise ReferenceDetectionError("Input image array is empty")

        if len(image.shape) == 3 and image.shape[2] == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        elif len(image.shape) == 2:
            gray = image
        else:
            raise ReferenceDetectionError(f"Unsupported image shape for marker detection: {image.shape}")

        corners_list, ids_arr, _ = self._detector.detectMarkers(gray)

        if ids_arr is None or len(corners_list) == 0:
            logger.debug("No ArUco markers detected in frame: %s", frame_path)
            return []

        filter_id = target_id if target_id is not None else self.target_marker_id
        observations: list[MarkerObservation] = []

        for corners_2d, mid in zip(corners_list, ids_arr.flatten()):
            marker_id_val = int(mid)
            if filter_id is not None and marker_id_val != filter_id:
                logger.debug(
                    "Skipping detected marker %d (target is %d) in %s",
                    marker_id_val,
                    filter_id,
                    frame_path,
                )
                continue

            # corners_2d shape is (1, 4, 2)
            pts = corners_2d.reshape((4, 2))
            c0 = (float(pts[0, 0]), float(pts[0, 1]))
            c1 = (float(pts[1, 0]), float(pts[1, 1]))
            c2 = (float(pts[2, 0]), float(pts[2, 1]))
            c3 = (float(pts[3, 0]), float(pts[3, 1]))

            # Calculate 2D edge lengths
            e01 = math.hypot(c1[0] - c0[0], c1[1] - c0[1])
            e12 = math.hypot(c2[0] - c1[0], c2[1] - c1[1])
            e23 = math.hypot(c3[0] - c2[0], c3[1] - c2[1])
            e30 = math.hypot(c0[0] - c3[0], c0[1] - c3[1])

            obs = MarkerObservation(
                marker_id=marker_id_val,
                corners_2d=(c0, c1, c2, c3),
                frame_path=frame_path,
                is_valid=True,
                edge_lengths_2d=[e01, e12, e23, e30],
            )
            observations.append(obs)

        return observations

    def detect_in_frames(
        self,
        frame_paths: Sequence[Path | str],
        target_id: Optional[int] = None,
    ) -> list[MarkerObservation]:
        """Detect markers across multiple keyframe files."""
        all_observations: list[MarkerObservation] = []
        for p in frame_paths:
            obs = self.detect_in_image(p, target_id=target_id)
            all_observations.extend(obs)
        return all_observations

    @staticmethod
    def generate_marker_image(
        dictionary_name: str = "DICT_4X4_50",
        marker_id: int = 0,
        size_px: int = 200,
        margin_px: int = 50,
    ) -> np.ndarray:
        """Utility to generate a clean synthetic ArUco marker image with quiet margin."""
        dict_id = resolve_aruco_dictionary(dictionary_name)
        dictionary = cv2.aruco.getPredefinedDictionary(dict_id)
        marker_img = cv2.aruco.generateImageMarker(dictionary, marker_id, size_px)
        if margin_px > 0:
            bordered = cv2.copyMakeBorder(
                marker_img,
                margin_px,
                margin_px,
                margin_px,
                margin_px,
                cv2.BORDER_CONSTANT,
                value=255,
            )
            return bordered
        return marker_img
