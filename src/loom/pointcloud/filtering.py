"""Point cloud downsampling and geometric filtering interfaces."""

from __future__ import annotations

from pathlib import Path


class PointCloudFilter:
    """Interface for spatial downsampling and normal estimation."""

    def voxel_downsample(self, pcd_path: Path, voxel_size: float, output_path: Path) -> Path:
        """Downsample point cloud using a regular voxel grid.

        Raises:
            NotImplementedError: Scheduled for Phase 3.
        """
        raise NotImplementedError("Point cloud voxel downsampling scheduled for Phase 3.")
