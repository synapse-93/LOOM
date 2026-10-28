
"""Overhang angle and support requirement analysis."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh


class OverhangAnalyzer:
    """Identifies faces that may require print supports."""

    def find_overhang_faces(
        self,
        mesh_path: Path,
        max_overhang_angle_deg: float = 45.0,
    ) -> list[int]:
        """Return face indices that may require support.

        Assumes the print bed is the XY plane and +Z is upward.
        The angle threshold is measured from vertically downward.
        """
        mesh_path = Path(mesh_path)

        if not mesh_path.is_file():
            raise FileNotFoundError(f"Mesh file not found: {mesh_path}")

        if not 0.0 <= max_overhang_angle_deg <= 90.0:
            raise ValueError("Overhang angle must be between 0 and 90 degrees.")

        mesh = trimesh.load(mesh_path, force="mesh", process=False)

        if not isinstance(mesh, trimesh.Trimesh):
            raise ValueError("Input file did not contain a valid mesh.")

        if len(mesh.faces) == 0:
            return []

        normals = np.asarray(mesh.face_normals, dtype=float)

        if not np.isfinite(normals).all():
            raise ValueError("Mesh contains invalid face normals.")

        # Angle from vertically downward: 0° is a downward-facing
        # horizontal surface; 90° is a vertical surface.
        downward_component = -normals[:, 2]
        angles = np.degrees(
            np.arccos(np.clip(downward_component, -1.0, 1.0))
        )

        # Flag downward-facing surfaces below the configured threshold.
        overhang_mask = (normals[:, 2] < 0.0) & (
            angles < max_overhang_angle_deg
        )

        return np.flatnonzero(overhang_mask).astype(int).tolist()
