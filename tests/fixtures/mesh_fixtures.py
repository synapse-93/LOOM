"""Deterministic test fixtures for Phase 3 Raw Geometry & Mesh Processing.

Generates realistic mesh fixtures with known ground-truth topological properties:
- Clean watertight cube (1 component, 0 holes, 0 degenerate faces)
- Disconnected mesh (2 components: primary cube + small satellite tetrahedron)
- Degenerate mesh (cube with zero-area collinear triangle)
- Hole mesh (cube with missing face, boundary defect of 3 edges)
- Large hole mesh (mesh with boundary loop > 30 edges, exceeds repair threshold)
- Duplicate / unreferenced geometry mesh (duplicated triangles, floating vertices)
- Corrupt / invalid mesh file
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import trimesh


def create_clean_cube() -> trimesh.Trimesh:
    """Create a clean, watertight cube with consistent outward normals.
    
    Properties:
    - Vertices: 8
    - Faces: 12
    - Components: 1
    - Boundary edges: 0
    - Watertight: True
    - Bounding Box: [-1, -1, -1] to [1, 1, 1], extents [2, 2, 2]
    - Volume: 8.0
    - Surface Area: 24.0
    """
    vertices = np.array([
        [-1.0, -1.0, -1.0],  # 0
        [ 1.0, -1.0, -1.0],  # 1
        [ 1.0,  1.0, -1.0],  # 2
        [-1.0,  1.0, -1.0],  # 3
        [-1.0, -1.0,  1.0],  # 4
        [ 1.0, -1.0,  1.0],  # 5
        [ 1.0,  1.0,  1.0],  # 6
        [-1.0,  1.0,  1.0],  # 7
    ], dtype=np.float64)

    faces = np.array([
        [0, 2, 1], [0, 3, 2],  # Bottom (-Z)
        [4, 5, 6], [4, 6, 7],  # Top (+Z)
        [0, 1, 5], [0, 5, 4],  # Front (-Y)
        [2, 3, 7], [2, 7, 6],  # Back (+Y)
        [0, 4, 7], [0, 7, 3],  # Left (-X)
        [1, 2, 6], [1, 6, 5],  # Right (+X)
    ], dtype=np.int64)

    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)


def create_disconnected_mesh() -> trimesh.Trimesh:
    """Create a mesh with two disconnected components.
    
    Component 1: Dominant cube (8 vertices, 12 faces) centered at origin.
    Component 2: Floating small tetrahedron (4 vertices, 4 faces) at [10, 10, 10].
    
    Properties:
    - Vertices: 12
    - Faces: 16
    - Components: 2
    """
    cube = create_clean_cube()
    
    # Small floating tetrahedron far away
    tet_vertices = np.array([
        [10.0, 10.0, 10.0],
        [11.0, 10.0, 10.0],
        [10.0, 11.0, 10.0],
        [10.0, 10.0, 11.0],
    ], dtype=np.float64)
    tet_faces = np.array([
        [0, 1, 2],
        [0, 2, 3],
        [0, 3, 1],
        [1, 3, 2],
    ], dtype=np.int64)
    
    # Combine
    combined_vertices = np.vstack([cube.vertices, tet_vertices])
    combined_faces = np.vstack([cube.faces, tet_faces + len(cube.vertices)])
    return trimesh.Trimesh(vertices=combined_vertices, faces=combined_faces, process=False)


def create_degenerate_mesh() -> trimesh.Trimesh:
    """Create a mesh containing degenerate (zero-area) faces.
    
    Appends a collinear triangle [0, 1, 2] where vertices lie on a line.
    
    Properties:
    - Vertices: 8 + 3 = 11 (or collinear vertices added)
    - Faces: 12 clean + 1 collinear zero-area = 13 faces
    - Degenerate faces: >= 1
    """
    cube = create_clean_cube()
    # Add a collinear zero-area triangle
    collinear_v = np.array([
        [0.0, 0.0, 2.0],
        [0.0, 0.0, 3.0],
        [0.0, 0.0, 4.0],
    ], dtype=np.float64)
    
    start_idx = len(cube.vertices)
    collinear_f = np.array([[start_idx, start_idx + 1, start_idx + 2]], dtype=np.int64)
    
    all_vertices = np.vstack([cube.vertices, collinear_v])
    all_faces = np.vstack([cube.faces, collinear_f])
    return trimesh.Trimesh(vertices=all_vertices, faces=all_faces, process=False)


def create_hole_mesh() -> trimesh.Trimesh:
    """Create a mesh with a small, reparable hole.
    
    Cube with 1 face removed.
    
    Properties:
    - Vertices: 8
    - Faces: 11 (1 face removed)
    - Boundary edges: 3
    - Boundary loops: 1 (3 edges)
    - Watertight: False
    - Repair candidate: Yes (<= max_hole_edges 30)
    """
    cube = create_clean_cube()
    # Remove the first face
    faces_with_hole = cube.faces[1:]
    return trimesh.Trimesh(vertices=cube.vertices.copy(), faces=faces_with_hole, process=False)


def create_large_hole_mesh(num_segments: int = 32) -> trimesh.Trimesh:
    """Create a mesh with a large boundary loop exceeding standard repair threshold.
    
    An open-topped cylinder or disc with 32 boundary edges on the open boundary loop.
    
    Properties:
    - Boundary edges: >= 32
    - Repair candidate under max_hole_edges=30: No (must be reported as unrepaired defect)
    """
    angles = np.linspace(0, 2 * np.pi, num_segments, endpoint=False)
    # Bottom center vertex 0
    bottom_center = np.array([[0.0, 0.0, 0.0]])
    # Rim vertices
    rim_vertices = np.column_stack([np.cos(angles), np.sin(angles), np.zeros(num_segments)])
    vertices = np.vstack([bottom_center, rim_vertices])
    
    # Fan faces connecting center to rim
    faces = []
    for i in range(num_segments):
        next_i = (i + 1) % num_segments
        faces.append([0, i + 1, next_i + 1])
    
    return trimesh.Trimesh(vertices=vertices, faces=np.array(faces, dtype=np.int64), process=False)


def create_duplicate_and_unreferenced_mesh() -> trimesh.Trimesh:
    """Create a mesh with duplicate faces and floating unreferenced vertices.
    
    Properties:
    - Clean cube (8 vertices, 12 faces)
    - + 1 duplicated face (identical to face 0)
    - + 2 floating vertices not connected to any face
    """
    cube = create_clean_cube()
    
    # Duplicate face 0
    dup_face = cube.faces[0:1].copy()
    all_faces = np.vstack([cube.faces, dup_face])
    
    # Add unreferenced vertices
    floating_v = np.array([
        [5.0, 5.0, 5.0],
        [6.0, 6.0, 6.0],
    ], dtype=np.float64)
    all_vertices = np.vstack([cube.vertices, floating_v])
    
    return trimesh.Trimesh(vertices=all_vertices, faces=all_faces, process=False)


def save_fixture_mesh(mesh: trimesh.Trimesh, path: Path, file_type: str = "obj") -> Path:
    """Save an in-memory trimesh to disk in specified format (obj, ply, stl)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(str(path), file_type=file_type)
    return path


def create_photogrammetry_raw_mesh(
    radius: float = 10.0,
    offset: tuple[float, float, float] = (105.4, 42.1, -210.8),
) -> trimesh.Trimesh:
    """Create a realistic photogrammetry raw reconstructed surface mesh.

    Models key artifacts typical of real-world Meshroom/AliceVision reconstructions:
    - Dominant multi-faceted body (icosphere surface, >1000 faces)
    - Open unobserved base resting surface (>30 boundary edges, unobserved by camera)
    - Small eligible surface pinhole/defect (3 boundary edges)
    - Floating disconnected photogrammetry background noise/dust components (2 clusters)
    - Collinear zero-area degenerate sliver triangles (from Marching Cubes/Delaunay)
    - Duplicate identical face
    - Floating unreferenced vertices
    - Non-origin arbitrary real-world SfM coordinate space
    """
    base = trimesh.creation.icosphere(subdivisions=3, radius=radius)
    centers = base.triangles_center

    # 1. Open ground boundary: remove bottom faces (z < -0.7 * radius)
    keep_mask = centers[:, 2] >= (-0.7 * radius)
    faces = base.faces[keep_mask].copy()

    # 2. Small surface defect: remove 1 face near equator
    mid_candidates = np.where(np.abs(centers[keep_mask, 2]) < 1.0)[0]
    mid_idx = mid_candidates[0] if len(mid_candidates) > 0 else 0
    faces = np.delete(faces, mid_idx, axis=0)

    vertices = base.vertices.copy()

    # 3. Add zero-area degenerate triangle sharing an edge of face 0
    v0 = vertices[faces[0, 0]]
    v1 = vertices[faces[0, 1]]
    v_mid = (v0 + v1) / 2.0
    v_mid_idx = len(vertices)
    vertices = np.vstack([vertices, [v_mid]])
    collinear_face = np.array([[faces[0, 0], faces[0, 1], v_mid_idx]], dtype=np.int64)
    faces = np.vstack([faces, collinear_face])

    # 4. Duplicate face
    faces = np.vstack([faces, faces[0:1]])

    # 5. Add two small disconnected satellite noise clusters ("dust")
    # Cluster 1: 4-face tetrahedron
    v_sat1 = np.array([
        [20.0, 20.0, 0.0],
        [22.0, 20.0, 0.0],
        [20.0, 22.0, 0.0],
        [20.0, 20.0, 2.0],
    ], dtype=np.float64)
    f_sat1 = np.array([
        [0, 1, 2],
        [0, 1, 3],
        [1, 2, 3],
        [2, 0, 3],
    ], dtype=np.int64) + len(vertices)
    vertices = np.vstack([vertices, v_sat1])
    faces = np.vstack([faces, f_sat1])

    # Cluster 2: 4-face tetrahedron
    v_sat2 = np.array([
        [-20.0, -20.0, 0.0],
        [-18.0, -20.0, 0.0],
        [-20.0, -18.0, 0.0],
        [-20.0, -20.0, 2.0],
    ], dtype=np.float64)
    f_sat2 = np.array([
        [0, 1, 2],
        [0, 1, 3],
        [1, 2, 3],
        [2, 0, 3],
    ], dtype=np.int64) + len(vertices)
    vertices = np.vstack([vertices, v_sat2])
    faces = np.vstack([faces, f_sat2])

    # 6. Floating unreferenced vertices
    v_unref = np.array([
        [50.0, 50.0, 50.0],
        [51.0, 51.0, 51.0],
        [52.0, 52.0, 52.0],
    ], dtype=np.float64)
    vertices = np.vstack([vertices, v_unref])

    # 7. Apply coordinate offset to place in realistic SfM world coordinate system
    vertices += np.array(offset, dtype=np.float64)

    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)

