"""Surface meshing and reconstruction interfaces from point clouds."""

from __future__ import annotations

from pathlib import Path


class SurfaceReconstructor:
    """Interface for generating watertight triangle meshes from oriented point clouds."""

    def poisson_surface_reconstruction(
        self,
        pcd_path: Path,
        output_mesh_path: Path,
        depth: int = 8,
    ) -> Path:
        """Execute Screened Poisson surface reconstruction.

        Raises:
            NotImplementedError: Scheduled for Phase 3.
        """
        raise NotImplementedError("Poisson surface reconstruction scheduled for Phase 3.")

    def ball_pivoting(
        self,
        pcd_path: Path,
        output_mesh_path: Path,
        radii: list[float],
    ) -> Path:
        """Execute Ball Pivoting surface reconstruction.

        Raises:
            NotImplementedError: Scheduled for Phase 3.
        """
        raise NotImplementedError("Ball pivoting reconstruction scheduled for Phase 3.")
