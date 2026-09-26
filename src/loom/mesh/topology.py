"""Mesh topological verification interfaces."""

from __future__ import annotations

from pathlib import Path


class MeshTopologyAnalyzer:
    """Interface for inspecting Euler characteristics, manifoldness, and genus."""

    def count_non_manifold_edges(self, mesh_path: Path) -> int:
        """Count edges shared by more than two faces or boundary edges.

        Raises:
            NotImplementedError: Scheduled for Phase 3.
        """
        raise NotImplementedError("Non-manifold edge counting scheduled for Phase 3.")

    def compute_euler_characteristic(self, mesh_path: Path) -> int:
        """Compute Euler characteristic (V - E + F).

        Raises:
            NotImplementedError: Scheduled for Phase 3.
        """
        raise NotImplementedError("Euler characteristic computation scheduled for Phase 3.")
