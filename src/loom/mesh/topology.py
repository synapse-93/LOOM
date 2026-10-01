"""Mesh topological verification interfaces."""

from __future__ import annotations

from pathlib import Path

from loom.mesh.diagnostics import MeshDiagnostics


class MeshTopologyAnalyzer:
    """Interface for inspecting Euler characteristics, manifoldness, and genus."""

    def count_non_manifold_edges(self, mesh_path: Path) -> int:
        """Count edges shared by more than two faces or boundary edges."""
        diag = MeshDiagnostics.inspect_file(mesh_path)
        return diag.non_manifold_edge_count

    def compute_euler_characteristic(self, mesh_path: Path) -> int:
        """Compute Euler characteristic (V - E + F)."""
        diag = MeshDiagnostics.inspect_file(mesh_path)
        return diag.euler_characteristic
