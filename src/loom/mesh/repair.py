"""Mesh repair and topological healing interfaces."""

from __future__ import annotations

from pathlib import Path


class MeshRepairer:
    """Interface for hole filling, normal unification, and edge stitching."""

    def fill_holes(self, mesh_path: Path, output_path: Path, max_hole_edges: int = 30) -> Path:
        """Detect and close open boundary loops on the mesh surface.

        Raises:
            NotImplementedError: Scheduled for Phase 3.
        """
        raise NotImplementedError("Mesh hole filling scheduled for Phase 3.")

    def unify_normals(self, mesh_path: Path, output_path: Path) -> Path:
        """Orient face normals consistently outwards.

        Raises:
            NotImplementedError: Scheduled for Phase 3.
        """
        raise NotImplementedError("Normal unification scheduled for Phase 3.")
