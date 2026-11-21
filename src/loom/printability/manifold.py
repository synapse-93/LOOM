"""Manifold geometry verification interfaces."""

from __future__ import annotations

from pathlib import Path
import numpy as np
import trimesh

from loom.utils.logging import get_logger

logger = get_logger("loom.printability.manifold")


class ManifoldChecker:
    """Verifies that a 3D mesh is a valid 2-manifold surface without non-manifold edges or vertices."""

    @staticmethod
    def _load_mesh(mesh_input: Path | str | trimesh.Trimesh) -> trimesh.Trimesh:
        """Load and resolve a trimesh.Trimesh instance from a path or object."""
        if isinstance(mesh_input, trimesh.Trimesh):
            return mesh_input
        p = Path(mesh_input).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"Input mesh file does not exist: {p}")
        loaded = trimesh.load(str(p), process=False)
        if isinstance(loaded, trimesh.Scene):
            if len(loaded.geometry) == 0:
                raise ValueError(f"Mesh file contains no geometry: {p}")
            return trimesh.util.concatenate(list(loaded.geometry.values()))
        return loaded

    def get_non_manifold_edge_count(self, mesh_path: Path | str | trimesh.Trimesh) -> int:
        """Count non-manifold edges (edges shared by more than two faces).

        In a 2-manifold triangle mesh, an edge must be incident to at most 2 faces.
        Edges shared by 3 or more faces form non-manifold junctions that cannot be 3D printed.
        """
        mesh = self._load_mesh(mesh_path)
        if len(mesh.faces) == 0:
            return 0
        edges = mesh.edges_sorted
        _, counts = np.unique(edges, axis=0, return_counts=True)
        return int(np.sum(counts > 2))

    def get_non_manifold_vertex_count(self, mesh_path: Path | str | trimesh.Trimesh) -> int:
        """Count non-manifold (pinched) vertices.

        A vertex is non-manifold if its incident 1-ring faces form more than one connected
        component sharing edges incident to the vertex (e.g. hourglass or two cones touching at apex).
        Uses vectorized vertex-to-face mapping and fast disjoint set union for linear performance.
        """
        mesh = self._load_mesh(mesh_path)
        if len(mesh.faces) == 0:
            return 0

        faces = mesh.faces
        v_indices = faces.ravel()
        f_indices = np.repeat(np.arange(len(faces)), 3)
        sort_idx = np.argsort(v_indices)
        sorted_v = v_indices[sort_idx]
        sorted_f = f_indices[sort_idx]
        unique_v, split_idx = np.unique(sorted_v, return_index=True)
        face_lists = np.split(sorted_f, split_idx[1:])

        non_manifold_count = 0
        for vi, fl in zip(unique_v, face_lists):
            if len(fl) <= 2:
                continue

            v_faces = faces[fl]
            other_edges: list[tuple[int, int]] = []
            for row in v_faces:
                other = [int(x) for x in row if x != vi]
                if len(other) == 2:
                    other_edges.append((other[0], other[1]))

            if not other_edges:
                continue

            parent: dict[int, int] = {}

            def find(x: int) -> int:
                root = x
                while parent[root] != root:
                    root = parent[root]
                curr = x
                while curr != root:
                    nxt = parent[curr]
                    parent[curr] = root
                    curr = nxt
                return root

            def union(x: int, y: int) -> None:
                rx, ry = find(x), find(y)
                if rx != ry:
                    parent[rx] = ry

            for x, y in other_edges:
                if x not in parent:
                    parent[x] = x
                if y not in parent:
                    parent[y] = y
                union(x, y)

            roots = {find(x) for x in parent}
            if len(roots) > 1:
                non_manifold_count += 1

        return non_manifold_count

    def is_edge_manifold(self, mesh_path: Path | str | trimesh.Trimesh) -> bool:
        """Check if every edge is shared by at most two faces."""
        return self.get_non_manifold_edge_count(mesh_path) == 0

    def is_vertex_manifold(self, mesh_path: Path | str | trimesh.Trimesh) -> bool:
        """Check if the neighborhood of every vertex is a single topological disk."""
        return self.get_non_manifold_vertex_count(mesh_path) == 0

    def is_manifold(self, mesh_path: Path | str | trimesh.Trimesh) -> bool:
        """Check if mesh has zero non-manifold edges and zero non-manifold vertices."""
        edge_ok = self.is_edge_manifold(mesh_path)
        vert_ok = self.is_vertex_manifold(mesh_path)
        return edge_ok and vert_ok

    def check_manifold(self, mesh_path: Path | str | trimesh.Trimesh) -> tuple[bool, int, int]:
        """Perform comprehensive manifold analysis.

        Returns:
            Tuple of (is_manifold, non_manifold_edge_count, non_manifold_vertex_count).
        """
        e_count = self.get_non_manifold_edge_count(mesh_path)
        v_count = self.get_non_manifold_vertex_count(mesh_path)
        return (e_count == 0 and v_count == 0), e_count, v_count
