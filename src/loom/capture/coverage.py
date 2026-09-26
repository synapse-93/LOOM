"""Visual viewpoint diversity and 2D frame coverage estimation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence
import cv2
import numpy as np

logger = logging.getLogger(__name__)


class CoverageEstimator:
    """Estimates 2D visual and viewpoint diversity across selected keyframes.

    Important:
        At Phase 1, this metric strictly represents 2D visual/viewpoint diversity
        across the captured keyframe sequence. True 3D geometric surface coverage
        is computed only after 3D reconstruction and surface meshing.
    """

    def estimate_coverage(self, keyframe_paths: Sequence[Path]) -> float:
        """Estimate 2D visual diversity score in range [0.0, 1.0].

        Args:
            keyframe_paths: List of selected keyframe images.

        Returns:
            Normalized diversity score from 0.0 (near-static/identical) to 1.0 (high diversity).
        """
        if not keyframe_paths:
            return 0.0
        if len(keyframe_paths) == 1:
            return 0.1

        # Sample small thumbnails across keyframes to compute pairwise variance
        thumbnails: list[np.ndarray] = []
        for p in keyframe_paths:
            gray = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
            if gray is not None:
                thumb = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA)
                thumbnails.append(thumb.astype(float))

        if len(thumbnails) < 2:
            return 0.1

        # Calculate mean consecutive difference across sequence
        differences: list[float] = []
        for i in range(1, len(thumbnails)):
            diff = float(np.mean(np.abs(thumbnails[i] - thumbnails[i - 1]))) / 255.0
            differences.append(diff)

        avg_diff = float(np.mean(differences)) if differences else 0.0
        # Map avg_diff (typically 0.02 - 0.25) to normalized score [0.0, 1.0]
        score = min(1.0, max(0.0, avg_diff * 4.0))
        return round(score, 3)
