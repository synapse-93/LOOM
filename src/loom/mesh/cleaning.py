"""Mesh cleaning, unreferenced vertex removal, and component filtering interfaces."""

from __future__ import annotations

from pathlib import Path


class MeshCleaner:
    """Interface for removing noise artifacts and disconnected mesh fragments."""

    def remove_isolated_components(self, mesh_path: Path, output_path: Path, min_faces: int = 100) -> Path:
        """Remove floating disconnected triangle clusters smaller than min_faces.

        Raises:
            NotImplementedError: Scheduled for Phase 3.
        """
        raise NotImplementedError("Mesh component cleaning scheduled for Phase 3.")

    def remove_unreferenced_vertices(self, mesh_path: Path, output_path: Path) -> Path:
        """Clean mesh by eliminating unreferenced vertices and zero-area faces.

        Raises:
            NotImplementedError: Scheduled for Phase 3.
        """
        raise NotImplementedError("Unreferenced vertex cleaning scheduled for Phase 3.")
