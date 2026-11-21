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


def split_into_simple_cycles(loop: list[int]) -> list[list[int]]:
    """Split a boundary loop (which may contain duplicate pinch vertices) into simple cycles."""
    simple_cycles: list[list[int]] = []
    stack: list[int] = []
    pos_map: dict[int, int] = {}
    for v in loop:
        if v in pos_map:
            idx = pos_map[v]
            cycle = stack[idx:]
            if len(cycle) >= 3:
                simple_cycles.append(cycle)
            for u in stack[idx:]:
                pos_map.pop(u, None)
            stack = stack[:idx]
        stack.append(v)
        pos_map[v] = len(stack) - 1
    if len(stack) >= 3:
        simple_cycles.append(stack)
    return simple_cycles


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
        current_faces = faces.copy()
        loops, boundary_edges = cls.extract_boundary_loops(current_faces)
        boundary_loops_before = len(loops)
        boundary_edges_before = len(boundary_edges)

        repairs_attempted = 0
        repairs_successful = 0
        defect_details: list[dict[str, Any]] = []
        new_faces: list[tuple[int, int, int]] = []
        v_arr = vertices.copy()
        existing_face_sets: set[frozenset[int]] = {frozenset(f) for f in faces}

        close_all = getattr(config, "close_all_holes", False)
        max_passes = 2 if close_all else 1

        extents = np.ptp(v_arr, axis=0) if len(v_arr) > 0 else np.zeros(3)
        total_bounding_perimeter = 2.0 * float(np.sum(extents))
        max_allowed_loop_perimeter = 0.25 * total_bounding_perimeter

        if boundary_loops_before > 0:
            logger.info("Detected %d boundary loops (%d boundary edges).", boundary_loops_before, boundary_edges_before)

            for pass_idx in range(max_passes):
                if pass_idx > 0:
                    loops, _ = cls.extract_boundary_loops(current_faces)
                    if not loops:
                        break

                all_cycles: list[list[int]] = []
                for l in loops:
                    all_cycles.extend(split_into_simple_cycles(l))

                pass_successful = 0
                for idx, cycle in enumerate(all_cycles):
                    loop_len = len(cycle)
                    cycle_pts = v_arr[cycle]
                    diffs = cycle_pts - np.roll(cycle_pts, -1, axis=0)
                    loop_perimeter = float(np.sum(np.linalg.norm(diffs, axis=1)))

                    # 1. Reject if boundary loop exceeds 25% of total mesh bounding perimeter
                    # (Elementary 3- and 4-edge holes are closed with 1 or 2 planar triangles without fan starbursts)
                    if loop_len > 4 and total_bounding_perimeter > 1e-6 and loop_perimeter > max_allowed_loop_perimeter:
                        reason = (
                            f"Loop perimeter ({loop_perimeter:.4f}) exceeds 25% of total mesh bounding perimeter "
                            f"({total_bounding_perimeter:.4f}, limit: {max_allowed_loop_perimeter:.4f})"
                        )
                        defect_details.append({
                            "loop_id": len(defect_details),
                            "edge_count": loop_len,
                            "perimeter": loop_perimeter,
                            "status": "UNREPAIRED",
                            "reason": reason,
                        })
                        logger.info("Rejecting hole repair for large boundary loop #%d: %s", len(defect_details) - 1, reason)
                        continue

                    # Anti-starburst guard: reject any boundary loop containing > 60 edges
                    if loop_len > 60:
                        reason = f"Boundary loop exceeds 60 edges ({loop_len} edges); rejected by anti-starburst guard."
                        defect_details.append({
                            "loop_id": len(defect_details),
                            "edge_count": loop_len,
                            "perimeter": loop_perimeter,
                            "status": "UNREPAIRED",
                            "reason": reason,
                        })
                        logger.info("Rejecting hole repair for large boundary loop #%d: %s", len(defect_details) - 1, reason)
                        continue

                    # 2. Check planarity of the boundary loop
                    is_planar = True
                    max_plane_dist = 0.0
                    normal = np.array([0.0, 0.0, 1.0])
                    centered = np.zeros_like(cycle_pts)
                    if loop_len >= 3:
                        centroid = np.mean(cycle_pts, axis=0)
                        centered = cycle_pts - centroid
                        try:
                            _, _, vh = np.linalg.svd(centered)
                            normal = vh[2]
                            max_plane_dist = float(np.max(np.abs(np.dot(centered, normal))))
                            max_ext = float(np.max(extents)) if len(extents) > 0 else 1.0
                            is_planar = (max_plane_dist <= 0.05 * max_ext) or (max_plane_dist <= 0.05 * loop_perimeter)
                        except Exception:
                            is_planar = True

                    if not is_planar and (loop_len > 10 or loop_perimeter > 0.10 * total_bounding_perimeter):
                        reason = (
                            f"Non-planar boundary loop ({loop_len} edges, perimeter {loop_perimeter:.4f}, "
                            f"max plane distance {max_plane_dist:.4f})"
                        )
                        defect_details.append({
                            "loop_id": len(defect_details),
                            "edge_count": loop_len,
                            "perimeter": loop_perimeter,
                            "status": "UNREPAIRED",
                            "reason": reason,
                        })
                        logger.info("Preserving non-planar boundary loop #%d: %s", len(defect_details) - 1, reason)
                        continue

                    # 3. Check configuration eligibility
                    if config.close_holes and (close_all or loop_len <= config.max_hole_edges):
                        repairs_attempted += 1
                        try:
                            k = len(cycle)
                            tri_indices: list[tuple[int, int, int]] = []
                            if k == 3:
                                tri_indices = [(cycle[0], cycle[1], cycle[2])]
                            elif k == 4:
                                tri_indices = [
                                    (cycle[0], cycle[1], cycle[2]),
                                    (cycle[0], cycle[2], cycle[3]),
                                ]
                            elif k <= 50:
                                loop_verts = v_arr[cycle]
                                tri_indices = cls._triangulate_loop(cycle, loop_verts)
                                if not tri_indices and k <= 12 and is_planar:
                                    c_idx = len(v_arr)
                                    centroid = np.mean(v_arr[cycle], axis=0)
                                    v_arr = np.vstack([v_arr, centroid])
                                    tri_indices = [(cycle[i], cycle[(i + 1) % k], c_idx) for i in range(k)]
                            else:
                                # For k > 50, attempt 2D planar mapbox-earcut if planar; never create giant starburst fan
                                if is_planar:
                                    try:
                                        import mapbox_earcut

                                        u_axis = np.cross(normal, np.array([1.0, 0.0, 0.0]) if abs(normal[0]) < 0.9 else np.array([0.0, 1.0, 0.0]))
                                        u_norm = np.linalg.norm(u_axis)
                                        if u_norm > 1e-9:
                                            u_axis /= u_norm
                                            v_axis = np.cross(normal, u_axis)
                                            pts_2d = np.column_stack([np.dot(centered, u_axis), np.dot(centered, v_axis)])
                                            pts_2d = np.ascontiguousarray(pts_2d, dtype=np.float64)
                                            rings = np.array([k], dtype=np.uint32)
                                            t_idx = mapbox_earcut.triangulate_float64(pts_2d, rings)
                                            if len(t_idx) >= 3:
                                                tri_indices = [(cycle[int(t_idx[ti])], cycle[int(t_idx[ti + 1])], cycle[int(t_idx[ti + 2])]) for ti in range(0, len(t_idx), 3)]
                                    except Exception:
                                        tri_indices = []

                            # Filter out any triangles that already exist to prevent non-manifold duplicate edges
                            valid_tris = []
                            for tri in tri_indices:
                                f_set = frozenset(tri)
                                if f_set not in existing_face_sets:
                                    valid_tris.append(tri)
                                    existing_face_sets.add(f_set)

                            if valid_tris:
                                new_faces.extend(valid_tris)
                                repairs_successful += 1
                                pass_successful += 1
                                defect_details.append({
                                    "loop_id": len(defect_details),
                                    "edge_count": loop_len,
                                    "perimeter": loop_perimeter,
                                    "status": "REPAIRED",
                                    "triangles_added": len(valid_tris),
                                })
                                logger.debug("Repaired boundary loop #%d (length %d) with %d triangles.", len(defect_details) - 1, loop_len, len(valid_tris))
                            else:
                                defect_details.append({
                                    "loop_id": len(defect_details),
                                    "edge_count": loop_len,
                                    "perimeter": loop_perimeter,
                                    "status": "UNREPAIRED",
                                    "reason": "Triangulation failed or degenerate loop geometry.",
                                })
                        except Exception as exc:
                            logger.warning("Failed to triangulate hole #%d: %s", len(defect_details), exc)
                            defect_details.append({
                                "loop_id": len(defect_details),
                                "edge_count": loop_len,
                                "perimeter": loop_perimeter,
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
                            "loop_id": len(defect_details),
                            "edge_count": loop_len,
                            "perimeter": loop_perimeter,
                            "status": "UNREPAIRED",
                            "reason": reason,
                        })
                        logger.info("Preserving open boundary loop #%d (length %d): %s", len(defect_details) - 1, loop_len, reason)

                if pass_successful > 0:
                    current_faces = np.vstack([faces, np.asarray(new_faces, dtype=np.int64)])
                else:
                    break

        # 2. Combine existing faces and newly generated repair faces
        if new_faces:
            all_faces = np.vstack([faces, np.asarray(new_faces, dtype=np.int64)])
        else:
            all_faces = faces

        repaired_mesh = trimesh.Trimesh(
            vertices=v_arr,
            faces=all_faces,
            process=False,
        )

        # 3. Normal unification if requested
        normals_unified = False
        if config.unify_normals and len(repaired_mesh.faces) > 0:
            normals_unified = cls._unify_normals_and_winding(repaired_mesh)

        if repaired_mesh.is_watertight and getattr(repaired_mesh, "volume", None) is not None:
            if repaired_mesh.volume < 0:
                repaired_mesh.faces = repaired_mesh.faces[:, ::-1]


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
            import warnings
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=RuntimeWarning)
                trimesh.repair.fix_normals(mesh)
                if mesh.is_watertight:
                    try:
                        if mesh.is_volume and mesh.volume < 0:
                            trimesh.repair.fix_inversion(mesh)
                    except Exception:
                        pass
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

    @classmethod
    def slice_and_cap_base(
        cls,
        mesh: trimesh.Trimesh,
        z_base: Optional[float] = None,
        bottom_percentile: float = 0.02,
        output_path: Optional[Path | str] = None,
    ) -> tuple[trimesh.Trimesh, dict[str, Any]]:
        """Slice geometry at Z_base and cleanly cap the planar boundary loop for 3D printing.

        Uses pure NumPy ear-clipping triangulation (no external shapely or C dependencies).
        Creates a completely flat contact surface for the build plate.

        Args:
            mesh: Input trimesh geometry.
            z_base: Explicit Z elevation at which to slice the geometry.
                    If None, computed from bottom_percentile.
            bottom_percentile: Bounding box percentile above minimum Z at which to slice (default: 0.02).
            output_path: Optional path to export intermediate mesh (e.g. 05_base_capped.ply).

        Returns:
            Tuple of (capped_mesh, result_dict) where result_dict contains capping metrics.
        """
        vertices = np.asarray(mesh.vertices, dtype=np.float64)
        faces = np.asarray(mesh.faces, dtype=np.int64)

        if len(faces) == 0 or len(vertices) == 0:
            return mesh, {
                "base_capped": False,
                "z_base": 0.0,
                "cap_faces_added": 0,
                "boundary_loops_capped": 0,
                "is_watertight": False,
                "output_path": None,
            }

        z_min = float(np.min(vertices[:, 2]))
        z_max = float(np.max(vertices[:, 2]))
        z_span = z_max - z_min

        if z_span <= 1e-8:
            return mesh, {
                "base_capped": False,
                "z_base": z_min,
                "cap_faces_added": 0,
                "boundary_loops_capped": 0,
                "is_watertight": mesh.is_watertight,
                "output_path": None,
            }

        if z_base is not None:
            target_z = float(z_base)
        else:
            target_z = z_min + bottom_percentile * z_span

        if target_z >= z_max:
            logger.warning("Base slicing Z (%.4f) >= maximum Z (%.4f); cannot slice mesh.", target_z, z_max)
            return mesh, {
                "base_capped": False,
                "z_base": target_z,
                "cap_faces_added": 0,
                "boundary_loops_capped": 0,
                "is_watertight": mesh.is_watertight,
                "output_path": None,
            }

        # Perturb target_z slightly if any vertex lies directly on it to prevent degenerate cut edges
        while np.any(np.abs(vertices[:, 2] - target_z) < 1e-6):
            target_z += 1e-5

        # 1. Triangle Slicing (pure NumPy)
        zv = vertices[:, 2]
        new_vertices = list(vertices.copy())
        new_faces: list[tuple[int, int, int]] = []
        edge_intersections: dict[tuple[int, int], int] = {}

        def get_intersection(u: int, v: int) -> int:
            key = (min(u, v), max(u, v))
            if key in edge_intersections:
                return edge_intersections[key]
            pu = vertices[u]
            pv = vertices[v]
            zu = pu[2]
            zv_val = pv[2]
            t = float((target_z - zu) / (zv_val - zu))
            p_inter = pu + t * (pv - pu)
            p_inter[2] = target_z
            idx = len(new_vertices)
            new_vertices.append(p_inter)
            edge_intersections[key] = idx
            return idx

        for f in faces:
            i0, i1, i2 = int(f[0]), int(f[1]), int(f[2])
            h0, h1, h2 = zv[i0], zv[i1], zv[i2]
            a0, a1, a2 = bool(h0 > target_z), bool(h1 > target_z), bool(h2 > target_z)
            k = int(a0) + int(a1) + int(a2)

            if k == 3:
                new_faces.append((i0, i1, i2))
            elif k == 0:
                continue
            elif k == 1:
                if a0:
                    vA, vB, vC = i0, i1, i2
                elif a1:
                    vA, vB, vC = i1, i2, i0
                else:
                    vA, vB, vC = i2, i0, i1
                I_AB = get_intersection(vA, vB)
                I_CA = get_intersection(vC, vA)
                new_faces.append((vA, I_AB, I_CA))
            elif k == 2:
                if not a2:
                    vA, vB, vC = i0, i1, i2
                elif not a0:
                    vA, vB, vC = i1, i2, i0
                else:
                    vA, vB, vC = i2, i0, i1
                I_BC = get_intersection(vB, vC)
                I_CA = get_intersection(vC, vA)
                new_faces.append((vA, vB, I_BC))
                new_faces.append((vA, I_BC, I_CA))

        v_arr = np.asarray(new_vertices, dtype=np.float64)
        sliced_faces = list(new_faces)
        existing_face_sets = {frozenset(f) for f in sliced_faces}

        # 2. Extract and triangulate boundary loops on sliced mesh
        loops, _ = cls.extract_boundary_loops(np.asarray(sliced_faces, dtype=np.int64))
        cap_faces: list[tuple[int, int, int]] = []
        loops_capped = 0

        for loop in loops:
            cycles = split_into_simple_cycles(loop)
            for c in cycles:
                c_pts = v_arr[c]
                is_on_base = bool(np.all(np.abs(c_pts[:, 2] - target_z) <= 1e-3))
                # Only cap the planar cut loop created by slicing at target_z
                if not is_on_base:
                    logger.debug("Skipping non-base boundary loop (%d edges) during planar base capping.", len(c))
                    continue

                k_c = len(c)
                cand_tris: list[tuple[int, int, int]] = []
                if k_c == 3:
                    cand_tris.append((c[0], c[1], c[2]))
                elif k_c == 4:
                    cand_tris.append((c[0], c[1], c[2]))
                    cand_tris.append((c[0], c[2], c[3]))
                else:
                    triangulated = False
                    # Prefer mapbox-earcut for fast, robust planar 2D triangulation
                    try:
                        import mapbox_earcut

                        pts_2d = np.ascontiguousarray(c_pts[:, :2], dtype=np.float64)
                        rings = np.array([k_c], dtype=np.uint32)
                        tri_indices = mapbox_earcut.triangulate_float64(pts_2d, rings)
                        if len(tri_indices) >= 3:
                            for t in range(0, len(tri_indices), 3):
                                idx0 = c[int(tri_indices[t])]
                                idx1 = c[int(tri_indices[t + 1])]
                                idx2 = c[int(tri_indices[t + 2])]
                                cand_tris.append((idx0, idx1, idx2))
                            triangulated = True
                    except Exception as earcut_err:
                        logger.debug("mapbox_earcut triangulation fallback: %s", earcut_err)

                    if not triangulated:
                        # Fallback to _ear_clip_2d
                        try:
                            pts_2d = np.ascontiguousarray(c_pts[:, :2], dtype=np.float64)
                            local_tris = cls._ear_clip_2d(pts_2d)
                            if local_tris:
                                for t0, t1, t2 in local_tris:
                                    cand_tris.append((c[t0], c[t1], c[t2]))
                                triangulated = True
                        except Exception as ear_err:
                            logger.debug("Pure ear clipping fallback: %s", ear_err)

                    if not triangulated:
                        c_idx = len(v_arr)
                        centroid = np.mean(c_pts, axis=0)
                        centroid[2] = target_z
                        v_arr = np.vstack([v_arr, centroid])
                        for i in range(k_c):
                            cand_tris.append((c[i], c[(i + 1) % k_c], c_idx))

                # For triangles on the base cut plane, ensure outward downward normals (n_z < 0)
                for tri in cand_tris:
                    idx0, idx1, idx2 = tri
                    p0, p1, p2 = v_arr[idx0], v_arr[idx1], v_arr[idx2]
                    cross_z = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p1[1] - p0[1]) * (p2[0] - p0[0])
                    if cross_z > 0:
                        tri = (idx0, idx2, idx1)
                    f_set = frozenset(tri)
                    if f_set not in existing_face_sets:
                        cap_faces.append(tri)
                        existing_face_sets.add(f_set)
                loops_capped += 1

        if cap_faces:
            all_faces = np.vstack([np.asarray(sliced_faces, dtype=np.int64), np.asarray(cap_faces, dtype=np.int64)])
        else:
            all_faces = np.asarray(sliced_faces, dtype=np.int64)

        capped_mesh = trimesh.Trimesh(
            vertices=v_arr,
            faces=all_faces,
            process=False,
        )

        # Prune small floating slivers generated along the planar cut boundary
        from loom.mesh.components import MeshComponentAnalyzer
        comps = MeshComponentAnalyzer.get_face_components(capped_mesh)
        if len(comps) > 1:
            total_faces = len(capped_mesh.faces)
            max_comp_faces = len(comps[0])
            if max_comp_faces > 1000:
                keep_faces = [idx for comp in comps if len(comp) >= max(10, 0.05 * max_comp_faces) for idx in comp]
                if len(keep_faces) > 0 and len(keep_faces) < total_faces:
                    capped_mesh = capped_mesh.submesh([keep_faces], append=True)

        if not capped_mesh.is_watertight:
            # Conservative defect repair: only close small planar defects (< 25% bounding perimeter)
            cfg_conservative = MeshConfig(fill_holes=True, max_hole_edges=30, close_all_holes=False)
            capped_mesh, _ = cls.repair(capped_mesh, cfg_conservative)

        try:
            trimesh.repair.fix_winding(capped_mesh)
        except Exception:
            pass
        capped_mesh.fix_normals()

        if capped_mesh.is_watertight and getattr(capped_mesh, "volume", None) is not None:
            if capped_mesh.volume < 0:
                capped_mesh.faces = capped_mesh.faces[:, ::-1]

        # Clean unreferenced vertices without altering surface topology
        capped_mesh.remove_unreferenced_vertices()
        cleaned_capped = capped_mesh

        if output_path is not None:
            out_p = Path(output_path).resolve()
            out_p.parent.mkdir(parents=True, exist_ok=True)
            cleaned_capped.export(out_p)
            logger.info("Exported base-capped intermediate mesh to: %s", out_p)

        logger.info(
            "Planar base capping complete at Z=%.4f: added %d cap faces across %d boundary loops.",
            target_z,
            len(cap_faces),
            loops_capped,
        )

        return cleaned_capped, {
            "base_capped": len(cap_faces) > 0,
            "z_base": target_z,
            "cap_faces_added": len(cap_faces),
            "boundary_loops_capped": loops_capped,
            "is_watertight": cleaned_capped.is_watertight,
            "output_path": Path(output_path).resolve() if output_path else None,
        }

    def cap_base(
        self,
        mesh_path: Path,
        output_path: Path,
        z_base: Optional[float] = None,
        bottom_percentile: float = 0.02,
    ) -> Path:
        """Slice mesh geometry at Z_base and cap boundary loop cleanly for 3D printing."""
        loaded = trimesh.load(mesh_path, process=False)
        if isinstance(loaded, trimesh.Scene):
            loaded = trimesh.util.concatenate(list(loaded.geometry.values()))
        capped, _ = self.slice_and_cap_base(
            mesh=loaded,
            z_base=z_base,
            bottom_percentile=bottom_percentile,
            output_path=output_path,
        )
        return output_path
