"""Conservative hole detection, defect analysis, and eligible repair."""

from __future__ import annotations

from collections import deque
import logging
from pathlib import Path
from typing import Any, Optional

import numpy as np
import trimesh

from loom.config.models import MeshConfig
from loom.mesh.models import RepairActionResult

logger = logging.getLogger(__name__)



class MeshRepairer:
    """Detects surface boundary loops (holes) and performs conservative planar/polygon repair."""

    def __init__(self, config: Optional[MeshConfig] = None) -> None:
        self.config = config or MeshConfig()

    def repair_mesh(
        self,
        mesh: Any = None,
        config: Optional[MeshConfig] = None,
    ) -> tuple[trimesh.Trimesh, RepairActionResult]:
        """Repair mesh defects (supports instance or class call)."""
        if isinstance(self, MeshRepairer):
            target_mesh = mesh
            target_config = config or self.config
        else:
            target_mesh = self
            target_config = mesh if isinstance(mesh, MeshConfig) else (config or MeshConfig())
        return MeshRepairer.repair(target_mesh, target_config)

    @classmethod
    def repair(
        cls,
        mesh: trimesh.Trimesh,
        config: MeshConfig,
    ) -> tuple[trimesh.Trimesh, RepairActionResult]:

        """Detect open boundary loops and conservatively fill eligible defects below threshold."""
        vertices = np.asarray(mesh.vertices, dtype=np.float64)
        faces = np.asarray(mesh.faces, dtype=np.int64)

        if len(faces) == 0 or len(vertices) == 0:
            return mesh, RepairActionResult(
                boundary_loops_before=0,
                boundary_edges_before=0,
                repairs_attempted=0,
                repairs_successful=0,
                remaining_boundary_loops=0,
                remaining_boundary_edges=0,
                normals_unified=False,
            )

        # 1. Detect boundary directed edges (the holes)
        loops, boundary_edges = cls.extract_boundary_loops(faces)
        boundary_loops_before = len(loops)
        boundary_edges_before = len(boundary_edges)

        repairs_attempted = 0
        repairs_successful = 0
        defect_details: list[dict[str, Any]] = []
        new_faces: list[tuple[int, int, int]] = []

        if boundary_loops_before > 0:
            logger.info("Detected %d boundary loops (%d boundary edges).", boundary_loops_before, boundary_edges_before)

            for idx, loop in enumerate(loops):
                loop_len = len(loop)
                # Check eligibility
                if config.close_holes and loop_len <= config.max_hole_edges:
                    repairs_attempted += 1
                    try:
                        loop_verts = vertices[loop]
                        tri_indices = cls._triangulate_loop(loop, loop_verts)
                        if tri_indices:
                            new_faces.extend(tri_indices)
                            repairs_successful += 1
                            defect_details.append({
                                "loop_id": idx,
                                "edge_count": loop_len,
                                "status": "REPAIRED",
                                "triangles_added": len(tri_indices),
                            })
                            logger.info("Repaired boundary loop #%d (length %d) with %d triangles.", idx, loop_len, len(tri_indices))
                        else:
                            defect_details.append({
                                "loop_id": idx,
                                "edge_count": loop_len,
                                "status": "UNREPAIRED",
                                "reason": "Triangulation failed or degenerate loop geometry.",
                            })
                    except Exception as exc:
                        logger.warning("Failed to triangulate hole #%d: %s", idx, exc)
                        defect_details.append({
                            "loop_id": idx,
                            "edge_count": loop_len,
                            "status": "UNREPAIRED",
                            "reason": str(exc),
                        })
                else:
                    # Defect exceeds size threshold or hole closing disabled
                    reason = (
                        f"Loop edge count ({loop_len}) exceeds max_hole_edges limit ({config.max_hole_edges})"
                        if config.close_holes
                        else "Hole closing disabled by configuration."
                    )
                    defect_details.append({
                        "loop_id": idx,
                        "edge_count": loop_len,
                        "status": "UNREPAIRED",
                        "reason": reason,
                    })
                    logger.info("Preserving open boundary loop #%d (length %d): %s", idx, loop_len, reason)

        # 2. Combine existing faces and newly generated repair faces
        if new_faces:
            all_faces = np.vstack([faces, np.asarray(new_faces, dtype=np.int64)])
        else:
            all_faces = faces

        repaired_mesh = trimesh.Trimesh(
            vertices=vertices,
            faces=all_faces,
            process=False,
        )

        # 3. Normal unification if requested
        normals_unified = False
        if config.unify_normals and len(repaired_mesh.faces) > 0:
            normals_unified = cls._unify_normals_and_winding(repaired_mesh)


        # 4. Measure remaining boundary loops and edges
        remaining_loops, remaining_edges = cls.extract_boundary_loops(repaired_mesh.faces)

        action_result = RepairActionResult(
            boundary_loops_before=boundary_loops_before,
            boundary_edges_before=boundary_edges_before,
            repairs_attempted=repairs_attempted,
            repairs_successful=repairs_successful,
            remaining_boundary_loops=len(remaining_loops),
            remaining_boundary_edges=len(remaining_edges),
            normals_unified=normals_unified,
            faces_added=len(new_faces),
            defect_details=defect_details,
        )


        logger.info(
            "Repair stage complete: boundary loops %d -> %d, attempted %d, successful %d",
            boundary_loops_before,
            len(remaining_loops),
            repairs_attempted,
            repairs_successful,
        )

        return repaired_mesh, action_result

    @classmethod
    def extract_boundary_loops(cls, faces: np.ndarray) -> tuple[list[list[int]], np.ndarray]:
        """Extract all closed boundary loops and boundary edges from face array."""
        if len(faces) == 0:
            return [], np.empty((0, 2), dtype=np.int64)

        directed_edges = np.vstack([
            faces[:, [0, 1]],
            faces[:, [1, 2]],
            faces[:, [2, 0]],
        ])
        sorted_edges = np.sort(directed_edges, axis=1)
        _, inv, counts = np.unique(sorted_edges, axis=0, return_inverse=True, return_counts=True)
        boundary_idx = np.where(counts[inv] == 1)[0]

        if len(boundary_idx) == 0:
            return [], np.empty((0, 2), dtype=np.int64)

        # On the missing face, directed edges run in reverse (v -> u)
        hole_directed = directed_edges[boundary_idx][:, [1, 0]]

        # Adjacency map: u -> [v1, v2...]
        adj: dict[int, list[int]] = {}
        for edge in hole_directed:
            u, v = int(edge[0]), int(edge[1])
            adj.setdefault(u, []).append(v)

        visited_edges: set[tuple[int, int]] = set()
        loops: list[list[int]] = []

        for edge in hole_directed:
            start_u, start_v = int(edge[0]), int(edge[1])
            if (start_u, start_v) in visited_edges:
                continue

            loop = [start_u]
            curr = start_v
            visited_edges.add((start_u, start_v))
            closed = False

            while curr in adj:
                loop.append(curr)
                next_node = None
                for cand in adj[curr]:
                    if (curr, cand) not in visited_edges:
                        next_node = cand
                        visited_edges.add((curr, cand))
                        break

                if next_node is None:
                    break
                if next_node == start_u:
                    closed = True
                    break
                curr = next_node

            if closed and len(loop) >= 3:
                loops.append(loop)

        return loops, sorted_edges[boundary_idx]

    @classmethod
    def _triangulate_loop(cls, loop: list[int], loop_verts: np.ndarray) -> list[tuple[int, int, int]]:
        """Triangulate a 3D polygon loop using 2D best-fit plane projection and ear clipping."""
        k = len(loop)
        if k < 3:
            return []
        if k == 3:
            return [(loop[0], loop[1], loop[2])]
        if k == 4:
            return [
                (loop[0], loop[1], loop[2]),
                (loop[0], loop[2], loop[3]),
            ]

        # Newell's method for normal of 3D polygon
        normal = np.zeros(3, dtype=np.float64)
        for i in range(k):
            v_curr = loop_verts[i]
            v_next = loop_verts[(i + 1) % k]
            normal[0] += (v_curr[1] - v_next[1]) * (v_curr[2] + v_next[2])
            normal[1] += (v_curr[2] - v_next[2]) * (v_curr[0] + v_next[0])
            normal[2] += (v_curr[0] - v_next[0]) * (v_curr[1] + v_next[1])

        norm_len = np.linalg.norm(normal)
        if norm_len <= 1e-12:
            # Degenerate loop; fall back to naive fan
            return [(loop[0], loop[i], loop[i + 1]) for i in range(1, k - 1)]

        normal /= norm_len

        # Construct orthonormal projection basis (u_axis, v_axis)
        arbitrary = np.array([1.0, 0.0, 0.0]) if abs(normal[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        u_axis = np.cross(normal, arbitrary)
        u_axis /= np.linalg.norm(u_axis)
        v_axis = np.cross(normal, u_axis)

        # Project 3D points to 2D
        pts_2d = np.column_stack([
            np.dot(loop_verts, u_axis),
            np.dot(loop_verts, v_axis),
        ])

        # Ear clip the 2D polygon
        triangles_local = cls._ear_clip_2d(pts_2d)
        if not triangles_local:
            # Fall back to fan triangulation
            return [(loop[0], loop[i], loop[i + 1]) for i in range(1, k - 1)]

        return [(loop[i0], loop[i1], loop[i2]) for i0, i1, i2 in triangles_local]

    @staticmethod
    def _ear_clip_2d(pts: np.ndarray) -> list[tuple[int, int, int]]:
        """Ear clipping triangulation for simple 2D polygons."""
        n = len(pts)
        if n < 3:
            return []
        if n == 3:
            return [(0, 1, 2)]

        indices = list(range(n))
        triangles: list[tuple[int, int, int]] = []

        # Check signed area for counter-clockwise orientation
        area = 0.5 * sum(
            pts[i, 0] * pts[(i + 1) % n, 1] - pts[(i + 1) % n, 0] * pts[i, 1]
            for i in range(n)
        )
        if area < 0:
            indices.reverse()

        def is_convex(i_prev: int, i_curr: int, i_next: int) -> bool:
            p0, p1, p2 = pts[i_prev], pts[i_curr], pts[i_next]
            return ((p1[0] - p0[0]) * (p2[1] - p0[1]) - (p1[1] - p0[1]) * (p2[0] - p0[0])) > 1e-12

        def point_in_tri(p: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> bool:
            v0 = c - a
            v1 = b - a
            v2 = p - a
            dot00 = np.dot(v0, v0)
            dot01 = np.dot(v0, v1)
            dot02 = np.dot(v0, v2)
            dot11 = np.dot(v1, v1)
            dot12 = np.dot(v1, v2)
            denom = dot00 * dot11 - dot01 * dot01
            if abs(denom) < 1e-12:
                return False
            inv = 1.0 / denom
            u = (dot11 * dot02 - dot01 * dot12) * inv
            v = (dot00 * dot12 - dot01 * dot02) * inv
            return (u >= 0) and (v >= 0) and (u + v < 1)

        iterations = 0
        max_iters = n * n
        while len(indices) > 3 and iterations < max_iters:
            iterations += 1
            m = len(indices)
            ear_found = False
            for i in range(m):
                prev_i = indices[(i - 1) % m]
                curr_i = indices[i]
                next_i = indices[(i + 1) % m]
                if is_convex(prev_i, curr_i, next_i):
                    a, b, c = pts[prev_i], pts[curr_i], pts[next_i]
                    has_point = False
                    for j in range(m):
                        test_i = indices[j]
                        if test_i not in (prev_i, curr_i, next_i):
                            if point_in_tri(pts[test_i], a, b, c):
                                has_point = True
                                break
                    if not has_point:
                        triangles.append((prev_i, curr_i, next_i))
                        indices.pop(i)
                        ear_found = True
                        break
            if not ear_found:
                break

        if len(indices) == 3:
            triangles.append((indices[0], indices[1], indices[2]))

        return triangles

    @classmethod
    def _unify_normals_and_winding(cls, mesh: trimesh.Trimesh) -> bool:
        """Unify face winding and compute outward normals using BFS without requiring networkx."""
        if len(mesh.faces) == 0:
            return False
        try:
            adj = mesh.face_adjacency
            edges = mesh.face_adjacency_edges
            if len(adj) > 0:
                adj_map: dict[int, list[tuple[int, int, int]]] = {}
                for (f1, f2), (v1, v2) in zip(adj, edges):
                    adj_map.setdefault(int(f1), []).append((int(f2), int(v1), int(v2)))
                    adj_map.setdefault(int(f2), []).append((int(f1), int(v1), int(v2)))

                visited: set[int] = set()
                faces = np.asarray(mesh.faces, dtype=np.int64).copy()
                for start_idx in range(len(faces)):
                    if start_idx in visited:
                        continue
                    visited.add(start_idx)
                    queue = deque([start_idx])
                    while queue:
                        curr = queue.popleft()
                        c_f = faces[curr]
                        c_edges = {(c_f[0], c_f[1]), (c_f[1], c_f[2]), (c_f[2], c_f[0])}
                        for nxt, v1, v2 in adj_map.get(curr, []):
                            if nxt not in visited:
                                c_dir = (v1, v2) in c_edges
                                n_f = faces[nxt]
                                n_edges = {(n_f[0], n_f[1]), (n_f[1], n_f[2]), (n_f[2], n_f[0])}
                                n_dir = (v1, v2) in n_edges
                                if c_dir == n_dir:
                                    faces[nxt] = faces[nxt, ::-1]
                                visited.add(nxt)
                                queue.append(nxt)
                mesh.faces = faces

            # Ensure normals are oriented consistently outwards
            trimesh.repair.fix_normals(mesh)
            if mesh.is_volume and mesh.volume < 0:
                trimesh.repair.fix_inversion(mesh)
            return True
        except Exception as exc:
            logger.debug("Normal and winding unification encountered issue: %s", exc)
            return False


    # -------------------------------------------------------------------------
    # Backward compatibility with Phase 0 scaffold interface
    # -------------------------------------------------------------------------

    def fill_holes(self, mesh_path: Path, output_path: Path, max_hole_edges: int = 30) -> Path:
        """Detect and close open boundary loops on the mesh surface."""
        loaded = trimesh.load(mesh_path, process=False)
        if isinstance(loaded, trimesh.Scene):
            loaded = trimesh.util.concatenate(list(loaded.geometry.values()))
        cfg = MeshConfig(close_holes=True, max_hole_edges=max_hole_edges)
        repaired, _ = self.repair(loaded, cfg)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        repaired.export(output_path)
        return output_path

    def unify_normals(self, mesh_path: Path, output_path: Path) -> Path:
        """Orient face normals consistently outwards."""
        loaded = trimesh.load(mesh_path, process=False)
        if isinstance(loaded, trimesh.Scene):
            loaded = trimesh.util.concatenate(list(loaded.geometry.values()))
        cfg = MeshConfig(close_holes=False, unify_normals=True)
        repaired, _ = self.repair(loaded, cfg)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        repaired.export(output_path)
        return output_path
