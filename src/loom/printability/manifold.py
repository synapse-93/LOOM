
"""Manifold geometry verification."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np
import trimesh


class ManifoldChecker:
    """Checks edge and vertex manifold properties of a mesh."""

    @staticmethod
    def _load_mesh(mesh_path: Path) -> trimesh.Trimesh:
        mesh_path = Path(mesh_path)

        if not mesh_path.is_file():
            raise FileNotFoundError(f"Mesh file not found: {mesh_path}")

        mesh = trimesh.load(mesh_path, force="mesh", process=False)

        if not isinstance(mesh, trimesh.Trimesh):
            raise ValueError("Input file did not contain a valid mesh.")

        return mesh

    def is_edge_manifold(self, mesh_path: Path) -> bool:
        """Return True if every edge belongs to one or two faces."""
        mesh = self._load_mesh(mesh_path)

        if len(mesh.faces) == 0:
            return False

        edge_counts = np.bincount(mesh.edges_unique_inverse)
        return bool(np.all((edge_counts >= 1) & (edge_counts <= 2)))

    def is_vertex_manifold(self, mesh_path: Path) -> bool:
        """Check that each used vertex has a connected fan of incident faces."""
        mesh = self._load_mesh(mesh_path)

        if len(mesh.faces) == 0 or len(mesh.vertices) == 0:
            return False

        faces = np.asarray(mesh.faces)

        edge_counts = np.bincount(mesh.edges_unique_inverse)
        if np.any(edge_counts > 2):
            return False

        incident_faces: dict[int, list[int]] = defaultdict(list)
        for face_index, face in enumerate(faces):
            if len(set(map(int, face))) != 3:
                return False

            for vertex in face:
                incident_faces[int(vertex)].append(face_index)

        # Every vertex link must be one connected cycle (interior vertex)
        # or one connected path (boundary vertex).
        for vertex, face_indices in incident_faces.items():
            link_adjacency: dict[int, set[int]] = defaultdict(set)

            for face_index in face_indices:
                face = faces[face_index]
                other_vertices = [
                    int(v) for v in face if int(v) != vertex
                ]

                if len(other_vertices) != 2:
                    return False

                a, b = other_vertices
                link_adjacency[a].add(b)
                link_adjacency[b].add(a)

            if not link_adjacency:
                return False

            degrees = [len(neighbors) for neighbors in link_adjacency.values()]

            # A cycle has all degree 2; a path has exactly two degree-1
            # endpoints and all remaining degrees equal to 2.
            if any(degree < 1 or degree > 2 for degree in degrees):
                return False

            endpoints = sum(degree == 1 for degree in degrees)
            if endpoints not in (0, 2):
                return False

            start = next(iter(link_adjacency))
            visited = set()
            stack = [start]

            while stack:
                current = stack.pop()
                if current in visited:
                    continue
                visited.add(current)
                stack.extend(link_adjacency[current] - visited)

            if len(visited) != len(link_adjacency):
                return False

        return True
