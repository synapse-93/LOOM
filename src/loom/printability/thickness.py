"""Minimum wall thickness verification interfaces."""

from __future__ import annotations

from pathlib import Path


class WallThicknessAnalyzer:
    """Estimates local mesh thickness to prevent thin-wall print failures."""

    def compute_minimum_thickness(self, mesh_path: Path) -> float:
        """Estimate minimum local wall thickness across the mesh geometry in mm.

        Raises:
            NotImplementedError: Scheduled for Phase 6.
        """
        raise NotImplementedError("Minimum wall thickness analysis scheduled for Phase 6.")
