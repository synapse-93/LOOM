"""Manifold geometry verification interfaces."""

from __future__ import annotations

from pathlib import Path


class ManifoldChecker:
    """Verifies that a 3D mesh is a valid 2-manifold surface."""

    def is_edge_manifold(self, mesh_path: Path) -> bool:
        """Check if every edge is shared by at most two faces.

        Raises:
            NotImplementedError: Scheduled for Phase 6.
        """
        raise NotImplementedError("Edge manifold checking scheduled for Phase 6.")

    def is_vertex_manifold(self, mesh_path: Path) -> bool:
        """Check if the neighborhood of every vertex is homeomorphic to a 2D disk.

        Raises:
            NotImplementedError: Scheduled for Phase 6.
        """
        raise NotImplementedError("Vertex manifold checking scheduled for Phase 6.")
