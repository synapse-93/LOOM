"""Metric transformation and coordinate rescaling interfaces."""

from __future__ import annotations

from pathlib import Path


class ScaleTransformer:
    """Applies metric scaling factors and orientation transforms to 3D meshes."""

    def apply_scale(self, mesh_path: Path, scale_factor: float, output_path: Path) -> Path:
        """Rescale mesh vertices to physical millimeters.

        Args:
            mesh_path: Input mesh path.
            scale_factor: Scalar multiplier (1.0 reconstructed unit = scale_factor millimeters).
            output_path: Path for output scaled mesh.

        Returns:
            Resolved Path to scaled mesh file.

        Raises:
            ValueError: If scale_factor <= 0.
            NotImplementedError: Scheduled for Phase 4.
        """
        if scale_factor <= 0.0:
            raise ValueError(f"Scale factor must be strictly positive, got {scale_factor}")
        raise NotImplementedError("Metric mesh rescaling scheduled for Phase 4.")
