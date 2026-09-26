"""Watertightness (closed volume) verification interfaces."""

from __future__ import annotations

from pathlib import Path


class WatertightChecker:
    """Verifies that a 3D mesh encloses a positive volume with no open boundary edges."""

    def is_watertight(self, mesh_path: Path) -> bool:
        """Check if mesh has zero boundary edges and enclosed volume.

        Raises:
            NotImplementedError: Scheduled for Phase 6.
        """
        raise NotImplementedError("Watertightness check scheduled for Phase 6.")
