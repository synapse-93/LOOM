"""Point cloud cleaning and outlier removal interfaces."""

from __future__ import annotations

from pathlib import Path


class PointCloudCleaner:
    """Interface for statistical and radius outlier removal in 3D point clouds."""

    def remove_outliers(
        self,
        pcd_path: Path,
        output_path: Path,
        nb_neighbors: int = 20,
        std_ratio: float = 2.0,
    ) -> Path:
        """Remove statistical outliers from point cloud.

        Raises:
            NotImplementedError: Scheduled for Phase 3.
        """
        raise NotImplementedError("Point cloud cleaning scheduled for Phase 3.")
