"""Point cloud spatial density and distribution analysis interfaces."""

from __future__ import annotations

from pathlib import Path


class PointCloudAnalyzer:
    """Interface for evaluating point density, spatial noise, and surface completeness."""

    def compute_density(self, pcd_path: Path) -> float:
        """Compute average spatial point density (points per mm^3 or normalized unit).

        Raises:
            NotImplementedError: Scheduled for Phase 3.
        """
        raise NotImplementedError("Point cloud density analysis scheduled for Phase 3.")
