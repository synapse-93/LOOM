"""ArUco fiducial marker detection interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class MarkerDetection:
    """Detected 2D/3D fiducial marker data."""

    marker_id: int
    corners_2d: tuple[
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
    ]
    frame_path: Path


class ArucoDetector:
    """Interface for detecting ArUco markers in captured video keyframes."""

    def __init__(self, dictionary_name: str = "DICT_4X4_50") -> None:
        self.dictionary_name = dictionary_name

    def detect_in_image(self, image_path: Path) -> list[MarkerDetection]:
        """Detect markers in a single image.

        Raises:
            NotImplementedError: Scheduled for Phase 4.
        """
        raise NotImplementedError("ArUco marker detection scheduled for Phase 4.")

    def detect_in_frames(self, frame_paths: Sequence[Path]) -> list[MarkerDetection]:
        """Detect markers across multiple keyframes.

        Raises:
            NotImplementedError: Scheduled for Phase 4.
        """
        raise NotImplementedError("Multi-frame marker detection scheduled for Phase 4.")
