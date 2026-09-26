"""Frame quality assessment interfaces for blur detection and sharpness scoring."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence
from loom.config.models import CaptureConfig


class FrameQualityAssessor:
    """Evaluates optical sharpness, motion blur, and illumination quality."""

    def __init__(self, config: CaptureConfig) -> None:
        self.config = config

    def compute_sharpness(self, frame_path: Path) -> float:
        """Compute sharpness score (e.g. Laplacian variance) for an image frame.

        Args:
            frame_path: Path to target frame image.

        Returns:
            Computed numerical sharpness score.

        Raises:
            NotImplementedError: Implementation scheduled for Phase 1.
        """
        raise NotImplementedError("Frame sharpness evaluation scheduled for Phase 1.")

    def filter_keyframes(self, frame_paths: Sequence[Path]) -> tuple[list[Path], list[Path]]:
        """Separate input frames into accepted keyframes and rejected blurry frames.

        Args:
            frame_paths: Sequence of candidate frame image paths.

        Returns:
            Tuple of (accepted_frames, rejected_frames).

        Raises:
            NotImplementedError: Implementation scheduled for Phase 1.
        """
        raise NotImplementedError("Keyframe filtering scheduled for Phase 1.")
