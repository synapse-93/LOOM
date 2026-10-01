"""Read-only geometry diagnostics and topological health inspection."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import trimesh

from loom.mesh.exceptions import MeshFormatError, MeshInvalidError, MeshLoadError
from loom.mesh.models import GeometryDiagnostics

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".obj", ".ply", ".stl"}


class MeshDiagnostics:
    """Read-only inspector for surface geometry, topology, and validity."""

    @classmethod
    def inspect(cls, mesh: trimesh.Trimesh, degenerate_area_threshold: float = 1e-7) -> GeometryDiagnostics:
        """Perform comprehensive read-only geometric and topological inspection of a mesh."""
        warnings: list[str] = []
        errors: list[str] = []

        vertices = np.asarray(mesh.vertices, dtype=np.float64)
        faces = np.asarray(mesh.faces, dtype=np.int64)

        vertex_count = len(vertices)
        face_count = len(faces)

        if vertex_count == 0 or face_count == 0:
            errors.append(f"Mesh has empty geometry: {vertex_count} vertices, {face_count} faces.")
            return GeometryDiagnostics(
                vertex_count=vertex_count,
                face_count=face_count,
                bounding_box_min=(0.0, 0.0, 0.0),
                bounding_box_max=(0.0, 0.0, 0.0),
                extents=(0.0, 0.0, 0.0),
                status="ERROR",
                errors=errors,
            )

        # 1. NaN and Infinite vertices
        nan_mask = np.isnan(vertices).any(axis=1)
        inf_mask = np.isinf(vertices).any(axis=1)
        nan_vertex_count = int(np.sum(nan_mask))
        infinite_vertex_count = int(np.sum(inf_mask))
        if nan_vertex_count > 0:
            errors.append(f"Detected {nan_vertex_count} vertices with NaN coordinates.")
        if infinite_vertex_count > 0:
            errors.append(f"Detected {infinite_vertex_count} vertices with Infinite coordinates.")

        # 2. Bounding Box and Extents (computed only on finite vertices)
        valid_vertex_mask = ~nan_mask & ~inf_mask
        if np.any(valid_vertex_mask):
            valid_verts = vertices[valid_vertex_mask]
            bb_min = tuple(float(x) for x in np.min(valid_verts, axis=0))
            bb_max = tuple(float(x) for x in np.max(valid_verts, axis=0))
            extents = tuple(float(b - a) for a, b in zip(bb_min, bb_max))
        else:
            bb_min = (0.0, 0.0, 0.0)
            bb_max = (0.0, 0.0, 0.0)
            extents = (0.0, 0.0, 0.0)

        # 3. Invalid face index checks
        invalid_face_count = 0
        if face_count > 0 and vertex_count > 0:
            out_of_bounds = (faces < 0) | (faces >= vertex_count)
            oob_mask = np.any(out_of_bounds, axis=1)
            # Repeated vertices within single face (e.g. [0, 0, 1])
            repeated_idx = (
                (faces[:, 0] == faces[:, 1])
                | (faces[:, 1] == faces[:, 2])
                | (faces[:, 0] == faces[:, 2])
            )
            invalid_face_mask = oob_mask | repeated_idx
            invalid_face_count = int(np.sum(invalid_face_mask))
            if invalid_face_count > 0:
                errors.append(f"Detected {invalid_face_count} faces with invalid or duplicate vertex indices.")

        # 4. Degenerate faces (zero-area triangles)
        degenerate_face_count = 0
        if face_count > 0 and invalid_face_count == 0 and nan_vertex_count == 0 and infinite_vertex_count == 0:
            try:
                v0 = vertices[faces[:, 0]]
                v1 = vertices[faces[:, 1]]
                v2 = vertices[faces[:, 2]]
                cross = np.cross(v1 - v0, v2 - v0)
                areas = 0.5 * np.linalg.norm(cross, axis=1)
                degenerate_face_count = int(np.sum(np.isnan(areas) | (areas <= degenerate_area_threshold)))
                if degenerate_face_count > 0:
                    warnings.append(f"Detected {degenerate_face_count} degenerate (zero-area) faces.")
            except Exception as e:
                logger.debug("Failed to calculate degenerate face areas: %s", e)

        # 5. Duplicate faces
        duplicate_face_count = 0
        if face_count > 0 and invalid_face_count == 0:
            sorted_faces = np.sort(faces, axis=1)
            unique_faces = np.unique(sorted_faces, axis=0)
            duplicate_face_count = int(face_count - len(unique_faces))
            if duplicate_face_count > 0:
                warnings.append(f"Detected {duplicate_face_count} duplicate faces.")

        # 6. Unreferenced vertices
        unreferenced_vertex_count = 0
        if face_count > 0 and invalid_face_count == 0:
            referenced_vertices = np.unique(faces)
            unreferenced_vertex_count = int(vertex_count - len(referenced_vertices))
            if unreferenced_vertex_count > 0:
                warnings.append(f"Detected {unreferenced_vertex_count} unreferenced (orphaned) vertices.")

        # 7. Boundary edges and Non-manifold edges
        boundary_edge_count = 0
        boundary_loop_count = 0
        non_manifold_edge_count = 0
        if face_count > 0 and invalid_face_count == 0:
            directed_edges = np.vstack([
                faces[:, [0, 1]],
                faces[:, [1, 2]],
                faces[:, [2, 0]],
            ])
            sorted_edges = np.sort(directed_edges, axis=1)
            _, inv, counts = np.unique(sorted_edges, axis=0, return_inverse=True, return_counts=True)
            edge_counts = counts[inv]

            boundary_indices = np.where(edge_counts == 1)[0]
            boundary_edge_count = int(len(boundary_indices) // 1)
            non_manifold_indices = np.where(edge_counts > 2)[0]
            non_manifold_edge_count = int(len(non_manifold_indices) // 3) if len(non_manifold_indices) > 0 else 0

            if boundary_edge_count > 0:
                warnings.append(f"Mesh has open surface: {boundary_edge_count} boundary edges.")
                # Count boundary loops
                boundary_directed = directed_edges[boundary_indices]
                boundary_loop_count = cls._count_boundary_loops(boundary_directed)

            if non_manifold_edge_count > 0:
                warnings.append(f"Detected {non_manifold_edge_count} non-manifold edges.")

        # 8. Connected components
        component_count = 1
        if face_count > 0 and invalid_face_count == 0 and nan_vertex_count == 0:
            try:
                if len(mesh.face_adjacency) > 0:
                    comps = trimesh.graph.connected_components(mesh.face_adjacency, min_len=1)
                    component_count = max(1, len(comps))
                else:
                    component_count = face_count
                if component_count > 1:
                    warnings.append(f"Mesh consists of {component_count} disconnected components.")
            except Exception as e:
                logger.debug("Component count via face adjacency failed: %s", e)

        # 9. Surface area and Volume
        surface_area: Optional[float] = None
        volume: Optional[float] = None
        if invalid_face_count == 0 and nan_vertex_count == 0:
            try:
                area_val = float(mesh.area)
                if not np.isnan(area_val) and area_val > 0:
                    surface_area = area_val
            except Exception:
                pass

            if mesh.is_watertight and boundary_edge_count == 0 and non_manifold_edge_count == 0:
                try:
                    vol_val = float(mesh.volume)
                    if not np.isnan(vol_val) and vol_val > 0:
                        volume = vol_val
                except Exception:
                    pass

        # 10. Euler characteristic: V - E + F
        euler_char = 0
        try:
            euler_char = int(vertex_count - len(mesh.edges_unique) + face_count)
        except Exception:
            pass

        # 11. Overall status determination
        if len(errors) > 0:
            status = "ERROR"
        elif len(warnings) > 0:
            status = "WARNING"
        else:
            status = "VALID"

        return GeometryDiagnostics(
            vertex_count=vertex_count,
            face_count=face_count,
            bounding_box_min=bb_min,
            bounding_box_max=bb_max,
            extents=extents,
            surface_area=surface_area,
            volume=volume,
            component_count=component_count,
            boundary_edge_count=boundary_edge_count,
            boundary_loop_count=boundary_loop_count,
            non_manifold_edge_count=non_manifold_edge_count,
            is_watertight=bool(mesh.is_watertight and boundary_edge_count == 0),
            is_winding_consistent=bool(mesh.is_winding_consistent),
            euler_characteristic=euler_char,
            nan_vertex_count=nan_vertex_count,
            infinite_vertex_count=infinite_vertex_count,
            invalid_face_count=invalid_face_count,
            degenerate_face_count=degenerate_face_count,
            duplicate_face_count=duplicate_face_count,
            unreferenced_vertex_count=unreferenced_vertex_count,
            status=status,
            warnings=warnings,
            errors=errors,
        )

    @classmethod
    def inspect_file(cls, mesh_path: Path) -> GeometryDiagnostics:
        """Load a mesh file and return its geometry diagnostics."""
        path = Path(mesh_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Mesh file does not exist: {mesh_path}")
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise MeshFormatError(
                f"Unsupported mesh format '{path.suffix}'. Supported formats: {sorted(SUPPORTED_EXTENSIONS)}"
            )

        try:
            loaded = trimesh.load(path, process=False)
            if isinstance(loaded, trimesh.Scene):
                # Flatten Scene into single Trimesh if multi-geometry
                if len(loaded.geometry) == 0:
                    raise MeshInvalidError(f"Mesh file contains no geometry: {mesh_path}")
                mesh = trimesh.util.concatenate(list(loaded.geometry.values()))
            elif isinstance(loaded, trimesh.Trimesh):
                mesh = loaded
            else:
                raise MeshLoadError(f"Loaded object is not a triangular mesh: {type(loaded)}")
        except (MeshFormatError, MeshInvalidError):
            raise
        except Exception as e:
            raise MeshLoadError(f"Failed to parse mesh file '{mesh_path}': {e}") from e

        return cls.inspect(mesh)

    @staticmethod
    def _count_boundary_loops(boundary_directed_edges: np.ndarray) -> int:
        """Trace directed boundary edges into closed loops and return the loop count."""
        if len(boundary_directed_edges) == 0:
            return 0

        # Build adjacency mapping for directed hole traversal (u -> [v1, v2...])
        adj: dict[int, list[int]] = {}
        for edge in boundary_directed_edges:
            u, v = int(edge[0]), int(edge[1])
            adj.setdefault(u, []).append(v)

        visited_edges: set[tuple[int, int]] = set()
        loops = 0

        for edge in boundary_directed_edges:
            start_u, start_v = int(edge[0]), int(edge[1])
            if (start_u, start_v) in visited_edges:
                continue

            # Trace loop
            curr = start_v
            visited_edges.add((start_u, start_v))
            closed = False

            while curr in adj:
                # Find an unvisited edge from curr
                next_node = None
                for candidate in adj[curr]:
                    if (curr, candidate) not in visited_edges:
                        next_node = candidate
                        visited_edges.add((curr, candidate))
                        break
                if next_node is None:
                    break
                if next_node == start_u:
                    closed = True
                    break
                curr = next_node

            if closed:
                loops += 1

        return max(1, loops) if len(boundary_directed_edges) > 0 and loops == 0 else loops
