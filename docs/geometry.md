# Phase 3 — Raw Geometry & Mesh Processing Specification

## 1. Executive Summary & Status Boundary

Phase 3 implements the geometry processing and mesh cleanup layer of LOOM / VIDEO2PRINT. It consumes a raw reconstructed 3D surface mesh (produced by photogrammetry backends or synthetic fixtures) and executes a deterministic, modular pipeline to produce a cleaned, topologically verified, coordinate-preserving intermediate mesh along with a comprehensive machine-readable report (`reports/geometry.json`).

> [!IMPORTANT]
> **Definitive Status Boundary**:
> - **Software Implementation**: COMPLETE
> - **Deterministic Fixture Validation**: VERIFIED (40 new unit & integration tests, 115 total tests passing)
> - **Physical Scale**: UNTOUCHED (Strictly preserved in original reconstruction coordinate units; Physical Metric Scaling is reserved for **Phase 4**)
> - **Live Reconstruction Integration**: AWAITING HOST RECONSTRUCTION BINARY (`ISSUE-BLK-002`)
> 
> The pipeline is completely functional and deterministic on real mesh fixtures (OBJ, PLY, STL). Live validation with end-to-end video-to-mesh output will be conducted once Meshroom or COLMAP is provisioned on the host.

---

## 2. Pipeline Sequence & Processing Stages

Phase 3 executes an 8-stage sequence managed by `MeshProcessor`:

```
RAW RECONSTRUCTED MESH (.obj, .ply, .stl)
                 │
                 ▼
┌───────────────────────────────────────────────┐
│ Stage 1: Input Validation & Ingest            │  Verify file existence, format support, parseability, min primitives
├───────────────────────────────────────────────┤
│ Stage 2: Initial Diagnostics (Before)         │  Compute vertex/face counts, bounding box, topology, defects (Read-only)
├───────────────────────────────────────────────┤
│ Stage 3: Connected Component Filtering        │  Analyze disjoint clusters; apply strategy (e.g. keep dominant)
├───────────────────────────────────────────────┤
│ Stage 4: Invalid & Degenerate Cleanup         │  Purge NaN/Inf vertices, invalid face indices, zero-area triangles, orphans
├───────────────────────────────────────────────┤
│ Stage 5: Conservative Defect & Hole Repair    │  Detect boundary loops; fill simple holes (<= max_hole_edges); report others
├───────────────────────────────────────────────┤
│ Stage 6: Mesh Normalization                   │  Recompute contiguous index arrays, outward normals; PRESERVE coordinates
├───────────────────────────────────────────────┤
│ Stage 7: Post-Processing Diagnostics (After)  │  Re-evaluate topology, watertightness, manifold edges, remaining warnings
├───────────────────────────────────────────────┤
│ Stage 8: Output Export & Report Generation    │  Export cleaned intermediate mesh to OBJ; write reports/geometry.json
└───────────────────────────────────────────────┘
                 │
                 ▼
CLEAN INTERMEDIATE MESH (`outputs/runs/<run_id>/geometry/cleaned_<stem>.obj`)
                 │
                 ▼
PHASE 4 (Fiducial Metric Scaling & Coordinate Transformation)
```

---

## 3. Strict Boundary & Non-Goals

Phase 3 is strictly scoped to raw geometry and mesh cleanup. In compliance with repository governance, Phase 3 **MUST NOT** perform:
- Metric scaling, millimeter conversion, or ArUco reference marker detection (reserved for **Phase 4**).
- Coordinate recentering, origin translation, or unit cube normalization (coordinates are strictly preserved for downstream scale recovery).
- CAD ground-truth dimensional comparison or accuracy benchmarking (reserved for **Phase 5**).
- Slicing, overhang analysis, or wall thickness calculation for 3D printing (reserved for **Phase 6**).
- Production STL export or manufacturing manifests (reserved for **Phase 7**).
- Introduction of PyTorch, NeRF, 3D Gaussian Splatting, Depth Anything, SAM, or neural AI dependencies.

---

## 4. Supported Formats & Input Contract

Phase 3 accepts standard 3D polygonal boundary surface meshes via `Path`:
- **Wavefront OBJ** (`.obj`): Fully supported with vertex indexing and face definitions.
- **Polygon File Format** (`.ply`): Supported in ASCII and binary forms.
- **Stereolithography** (`.stl`): Supported in ASCII and binary forms.

### Input Validation Rules
Input validation is performed prior to any processing:
1. File must exist and resolve to a regular file (`FileNotFoundError` on failure).
2. File extension must match supported formats (`MeshFormatError` on failure).
3. File must be non-empty and parseable by the geometry backend (`MeshInvalidError` or `MeshLoadError`).
4. Mesh must contain at least 3 vertices and 1 face (`MeshInvalidError` on failure).

---

## 5. Geometry Diagnostics (`MeshDiagnostics`)

Before and after processing, `MeshDiagnostics.inspect()` gathers read-only topological and geometric metrics without altering the mesh:

| Category | Diagnostic Metric | Description |
| :--- | :--- | :--- |
| **Primitives** | `vertex_count`, `face_count` | Raw counts of 3D points and triangular facets. |
| **Extents** | `bounding_box_min`, `bounding_box_max`, `extents` | Axis-aligned bounding box and coordinate spans along X, Y, Z. |
| **Physical Geometry**| `surface_area`, `volume` | Surface area and enclosed volume (when watertight). |
| **Topology** | `component_count` | Number of disjoint connected components. |
| | `boundary_edge_count`, `boundary_loop_count` | Edges belonging to exactly 1 face; open boundary perimeter loops. |
| | `non_manifold_edge_count` | Edges shared by 3 or more faces. |
| | `is_watertight` | Whether surface forms a closed, 2-manifold solid. |
| | `euler_characteristic` | Topological invariant: $V - E + F$. |
| **Validity** | `nan_vertex_count`, `infinite_vertex_count` | Vertices containing NaN or Inf coordinate components. |
| | `invalid_face_count` | Faces referencing out-of-bounds vertex indices or repeated vertices. |
| | `degenerate_face_count` | Triangles with zero surface area ($area \le 10^{-12}$). |
| | `duplicate_face_count` | Redundant identical triangles sharing vertex sets. |
| | `unreferenced_vertex_count` | Orphan vertices not referenced by any triangular face. |
| **Status** | `status` | Categorization: `VALID` (clean solid), `WARNING` (open boundaries or degeneracies), `ERROR` (corrupt NaN/Inf coordinates). |

---

## 6. Connected Component Analysis (`MeshComponentAnalyzer`)

Photogrammetry frequently yields floating reconstruction artifacts (background clusters, ground fragments). Disconnected components are identified using sparse graph traversal on face adjacency without external heavy dependencies.

### Configurable Filtering Strategies
- **`largest`** (Default): Keeps only the dominant component by triangular face count; discards satellite fragments.
- **`largest_by_area`**: Keeps the component with the largest total 3D surface area.
- **`min_faces`**: Discards any component with face count below `min_component_faces` (default: 100).
- **`relative_threshold`**: Retains components having at least `min_component_ratio` fraction of the dominant component's face count (default: 0.05).
- **`keep_all`**: Retains all components without filtering.

### Transparent Reporting
`ComponentActionResult` tracks:
- `components_before`, `components_after`
- `removed_components`, `removed_faces`, `removed_vertices`
- Detailed per-component breakdown (`ComponentInfo`).

---

## 7. Invalid & Degenerate Cleanup (`MeshCleaner`)

`MeshCleaner` provides deterministic, conservative cleanup of geometrically invalid primitives:
1. **NaN / Infinite Coordinate Removal**: Purges invalid float vertices and any incident faces.
2. **Invalid Face Index Removal**: Purges triangles referencing non-existent or duplicate vertex indices.
3. **Degenerate Face Removal**: Purges collinear, zero-area triangles using cross-product area evaluation ($0.5 \times \|(v_1 - v_0) \times (v_2 - v_0)\| \le 10^{-12}$).
4. **Duplicate Face Removal**: Sorts vertex references and keeps unique faces only.
5. **Orphan Vertex Removal**: Re-indexes vertex arrays to eliminate unreferenced vertices.

> [!NOTE]
> Coordinate values of surviving geometry are strictly preserved. No vertex smoothing, decimation, or position deformation is applied during this stage.

---

## 8. Conservative Hole & Defect Repair (`MeshRepairer`)

Phase 3 adheres strictly to **conservative hole repair**:
- Reconstructed surfaces may legitimately possess open boundaries (e.g. the uncaptured bottom of an object).
- Blindly closing every hole risks distorting the authentic reconstructed shape.

### Repair Criteria & Behavior
1. **Loop Detection**: Extracts directed boundary edges from faces and constructs ordered vertex boundary loops.
2. **Eligibility Evaluation**:
   - Loops with edge count $\le \text{max\_hole\_edges}$ (default: 30) are deemed **eligible**.
   - Loops with edge count $> \text{max\_hole\_edges}$ are deemed **ineligible** and preserved as open boundaries.
3. **Polygon Triangulation**: Eligible loops are projected onto their best-fit 2D plane and triangulated using robust ear-clipping.
4. **Outward Normal Unification**: Face winding is propagated consistently via breadth-first search across adjacent faces, ensuring outward-pointing normals.
5. **Honest Reporting**: Ineligible or failed loops are explicitly documented in `defect_details` with the reason for preservation.

---

## 9. Configuration Schema (`MeshConfig`)

Mesh processing behavior is configured via `MeshConfig` within `LoomConfig` or YAML:

```yaml
mesh:
  clean_outliers: true
  close_holes: true
  fill_holes: true
  max_hole_size: 30
  max_hole_edges: 30
  component_strategy: "largest"  # Options: largest, largest_by_area, min_faces, relative_threshold, keep_all
  min_component_faces: 100
  min_component_ratio: 0.05
  remove_degenerate_faces: true
  remove_unreferenced_vertices: true
  remove_duplicate_faces: true
  unify_normals: true
```

---

## 10. CLI Usage

Run Phase 3 processing directly via the LOOM CLI:

### Standalone Geometry Subcommand
```bash
python -m loom geometry --input path/to/raw_mesh.obj --output-dir outputs/my_run
```

### Direct Flag Execution
```bash
python -m loom --mesh path/to/raw_mesh.ply
```

### Terminal Output Sample
```
=================================================================
LOOM GEOMETRY PROCESSING - Phase 3 Summary
=================================================================
Input Mesh:             hole.obj

Initial Diagnostics:
  Vertices:             8
  Faces:                11
  Components:           1
  Boundary Edges:       3
  Boundary Loops:       1
  Degenerate Faces:     0
  Duplicate Faces:      0
  Unreferenced Verts:   0
  Status:               WARNING

Processing Actions:
  [OK] Validate mesh and load geometry
  [OK] Component filtering (largest): removed 0 components
  [OK] Invalid/degenerate cleanup: removed 0 degenerate, 0 unreferenced
  [OK] Conservative repair: attempted 1, successfully closed 1 loops
  [OK] Mesh normalization and outward normal unification

Cleaned Mesh Diagnostics:
  Vertices:             8
  Faces:                12
  Components:           1
  Boundary Edges:       0
  Boundary Loops:       0
  Watertight:           True
  Status:               VALID

Outputs:
  Cleaned Intermediate: outputs/runs/run_20261001_213321_hole/geometry/cleaned_hole.obj
  Geometry Report JSON: outputs/runs/run_20261001_213321_hole/reports/geometry.json
  Execution Time:       0.0073 seconds
-----------------------------------------------------------------
Status: SUCCESS
=================================================================
```

---

## 11. Deterministic Fixture Dataset & Verification

To verify Phase 3 without requiring live photogrammetry, `tests/fixtures/mesh_fixtures.py` programmatically constructs realistic test fixtures with known ground-truth topological defects:

1. **`clean_cube`**: Watertight cube (8 vertices, 12 faces, 0 holes, 0 degenerate faces, volume = 8.0, area = 24.0).
2. **`disconnected_mesh`**: Multi-component fixture (dominant cube of 12 faces + detached floating tetrahedron of 4 faces at $[10, 10, 10]$).
3. **`degenerate_mesh`**: Cube with an extra collinear zero-area triangle ($area \le 10^{-12}$).
4. **`hole_mesh`**: Cube missing 1 face (3 boundary edges forming 1 loop; verified closed back to 12 faces and watertightness restored).
5. **`large_hole_mesh`**: Cylinder rim with 32 boundary edges exceeding standard repair thresholds; verified preserved and reported in `defect_details`.
6. **`duplicate_and_unreferenced_mesh`**: Cube with duplicate face definitions and floating orphan vertices; verified purged while keeping core geometry intact.

### Test Coverage Summary
- **Phase 3 Diagnostics Tests**: 9 passed
- **Phase 3 Component Analysis Tests**: 6 passed
- **Phase 3 Geometry Cleanup Tests**: 5 passed
- **Phase 3 Defect Repair Tests**: 4 passed
- **Phase 3 Processor Orchestration Tests**: 11 passed
- **Phase 3 Integration & CLI Tests**: 5 passed
- **Total Test Suite**: 115 passing tests (0 failures, 0 regressions).
