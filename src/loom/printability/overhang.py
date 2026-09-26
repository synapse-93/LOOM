"""Overhang angle and support requirement analysis interfaces."""

from __future__ import annotations

from pathlib import Path


class OverhangAnalyzer:
    """Analyzes face normals relative to print bed Z-axis to identify support requirements."""

    def find_overhang_faces(
        self,
        mesh_path: Path,
        max_overhang_angle_deg: float = 45.0,
    ) -> list[int]:
        """Return list of face indices requiring print support material.

        Raises:
            NotImplementedError: Scheduled for Phase 6.
        """
        raise NotImplementedError("Overhang angle analysis scheduled for Phase 6.")
