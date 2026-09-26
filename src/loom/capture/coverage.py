"""Angular and visual coverage estimation interfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence


class CoverageEstimator:
    """Estimates visual viewpoint coverage and overlap across keyframe images."""

    def estimate_coverage(self, keyframe_paths: Sequence[Path]) -> float:
        """Estimate angular coverage score in range [0.0, 1.0].

        Args:
            keyframe_paths: List of selected keyframe images.

        Returns:
            Normalized coverage score from 0.0 (severely incomplete) to 1.0 (full 360 orbit).

        Raises:
            NotImplementedError: Implementation scheduled for Phase 7.
        """
        raise NotImplementedError("Viewpoint coverage estimation scheduled for Phase 7.")
