# ISSUES & TECHNICAL DEBT LOG — VIDEO2PRINT

This document tracks active blockers, known limitations, technical debt, research questions, and resolved issues discovered during repository inspection and development.

---

## 1. Active Blockers

*No active blockers. Native COLMAP 4.2.0 with CUDA 13.4 is operational on the Linux host with RTX 4060 GPU.*


---

## 2. Known Limitations

- **ISSUE-LIM-001: External Reconstruction Software Not Present in System PATH**
  - **Discovered**: 2026-09-26 (Repository inspection)
  - **Description**: Neither Meshroom (`meshroom_batch`), AliceVision binaries, nor COLMAP are currently found in the system `PATH` or standard Windows Program Files.
  - **Impact**: Does not block Phase 1 (video extraction and frame quality). Blocks Phase 2 live photogrammetry execution until binaries are installed or their path is configured.
  - **Mitigation**: Implement mock/stub fixtures for unit testing. Provide clear configuration parameters (`meshroom_binary_path`) so the adapter can point to custom installation directories.

- **ISSUE-LIM-002: Inherent Metric Scale Ambiguity in Monocular SfM**
  - **Discovered**: 2026-09-26 (Domain analysis)
  - **Description**: Monocular video footage does not encode metric baseline information. SfM solves for relative geometry up to an arbitrary scale factor $s$.
  - **Impact**: Output 3D meshes cannot be directly sent to a 3D printer without metric scaling (an unscaled mesh may be 0.05 mm or 5000 mm).
  - **Mitigation**: Addressed by ADR-004. A known physical fiducial (ArUco marker) must be included in the development capture workflow to recover physical millimeters.

- **ISSUE-LIM-003: System PATH Defaults to Python 3.14 Rather Than Python 3.10**
  - **Discovered**: 2026-09-26 (Repository inspection)
  - **Description**: Invoking generic `python` executes Python 3.14.7, which lacks binary wheels for `open3d` and `pymeshlab`. Python 3.10.11 is present on the machine under `py -3.10`.
  - **Impact**: Attempting to create a virtual environment with generic `python -m venv` will build a Python 3.14 environment that will fail wheel installations.
  - **Mitigation**: Always create the project virtual environment explicitly using `py -3.10 -m venv .venv`.

- **ISSUE-LIM-004: Video Codec FourCC Reporting Across Operating Systems**
  - **Discovered**: 2026-09-26 (Phase 1 Ingest Implementation)
  - **Description**: OpenCV `CAP_PROP_FOURCC` returns integer FourCC codes that can produce non-printable characters or 0 on Windows Media Foundation (MSMF) backends.
  - **Impact**: Codec string in `metadata.json` may report `"unknown"` or generic container type for certain smartphone containers.
  - **Mitigation**: `extract_video_metadata` safely filters non-printable characters and gracefully falls back to `"unknown"`, preserving all other critical stream parameters (FPS, frame count, width, height, duration).

- **ISSUE-LIM-005: Global Redundancy Thumbnail Sensitivity to Scene Background**
  - **Discovered**: 2026-09-26 (Phase 1 Redundancy Filter Tuning)
  - **Description**: When a small target object moves against a large static background, global thumbnail mean difference is only ~2-3% (similarity 0.97-0.98). A threshold of 0.95 would discard valid orbital camera steps.
  - **Impact**: Strict similarity thresholds could prematurely discard useful viewpoint frames.
  - **Mitigation**: Standardized `redundancy_threshold` default to 0.98 and preserved full configurability via `CaptureConfig`.

---

## 3. Technical Debt

*No technical debt currently identified. The codebase is greenfield.*

---

## 4. Research Questions

- **RQ-001**: What is the optimal frame selection threshold (Laplacian variance vs. inter-frame optical flow / feature overlap) that minimizes SfM computation time without degrading surface mesh completeness?
- **RQ-002**: What is the minimum physical fiducial marker size relative to the field of view required to recover metric scale with less than 2.0% dimensional error across varying smartphone camera angles?
- **RQ-003**: How do surface reconstruction algorithms (e.g. Screened Poisson vs. Ball Pivoting) compare in producing watertight, manifold meshes from sparse/dense point clouds of real-world objects?

---

## 5. Resolved Issues

- **ISSUE-RES-000: Project Bootstrap & Architectural Baseline Setup**
  - **Resolved**: 2026-09-26 (Iteration 000)
  - **Description**: Workspace was an empty repository with no governance or rules.
  - **Resolution**: Created `AGENTS.md`, `.agents/rules/`, and `project/` documentation structures establishing project memory and rules.

- **ISSUE-RES-001: Python 3.10.11 Environment Setup & Toolchain Activation**
  - **Resolved**: 2026-09-26 (Iteration 001)
  - **Description**: Windows `py` launcher registry listed Python 3.10 at a non-existent path on disk.
  - **Resolution**: Installed Python 3.10.11 via `winget`, created isolated virtual environment `.venv`, installed minimal dependencies (`pyyaml`, `pytest`), installed package in editable mode, and verified complete test suite.

- **ISSUE-RES-002: Photogrammetry Toolchain Activated with Native CUDA COLMAP 4.2.0**
  - **Resolved**: 2026-11-09 (Iteration 013)
  - **Description**: External reconstruction binaries were previously missing.
  - **Resolution**: Verified native `/usr/bin/colmap` (COLMAP 4.2.0 with CUDA 13.4 and RTX 4060 GPU). Configured dynamic library paths (`/opt/cuda/lib64`), resolved `ColmapAdapter` pipeline, and verified unit/integration testing suite.

- **ISSUE-RES-003: Video Reconstruction Turnaround Bottleneck (Mapper CPU & Exhaustive Matching)**
  - **Resolved**: 2026-11-09 (Iteration 015)
  - **Description**: Processing 300 sequential video frames through exhaustive matching evaluated ~44,850 image pairs, and unbounded Ceres bundle adjustment in `colmap mapper` stalled on redundant baselines (> 25 min runtime).
  - **Resolution**: Implemented Laplacian blur filtering ($\text{Var}(\nabla^2 I) < 20.0$) with sharp adjacent fallback and 75-keyframe even striding in `frames.py`. Switched to GPU `sequential_matcher` with loop closure (`--SequentialMatching.overlap 10`, quadratic overlap, loop detection) in `colmap.py`. Enforced 16-thread CPU pinning and bounded Ceres iterations (`ba_global_max_num_iterations 20`, `ba_local_max_num_iterations 15`). Purged stale workspace databases per run. Expected turnaround reduced to < 4 minutes.

- **ISSUE-RES-004: Empty Poisson Mesh Generation & Stereo Point Culling**
  - **Resolved**: 2026-11-09 (Iteration 016)
  - **Description**: `colmap poisson_mesher` ran with default `--PoissonMeshing.trim 10`, deleting 100% of triangles on sparse boundary regions and generating a 248-byte empty file with 0 vertices, causing Phase 3 geometry repair to crash with `Mesh file contains no geometry`. Simultaneously, default `--StereoFusion.min_num_pixels 5` aggressively pruned valid stereo points.
  - **Resolution**: Updated `ColmapAdapter` stereo fusion arguments to `--StereoFusion.min_num_pixels 2` and `--StereoFusion.max_image_size 1600`. Updated Poisson mesher arguments to `--PoissonMeshing.trim 0`, `--PoissonMeshing.depth 10`, and `--PoissonMeshing.point_weight 1.0`. Implemented automatic fallback in `reconstruct_dense()` to dense Delaunay meshing (`colmap delaunay_mesher --input_type dense`) if Poisson mesher produces 0 vertices or crashes. Added `--min-num-pixels` CLI flag in `scripts/demo.py`. Verified via unit tests.

- **ISSUE-RES-005: Out-Of-Memory (OOM) via mesh.split() and Centroid Noise Speck Selection**
  - **Resolved**: 2026-11-10 (Iteration 017)
  - **Description**: Calling `mesh.split(only_watertight=False)` across 495 connected components on 1M-face meshes allocated ~7 GB of RAM and triggered Linux kernel OOM kills. Simultaneously, centroid distance calculation using whole-mesh bounding box midpoint selected a 122-face noise speck and discarded the 1,035,175-face shoe. Furthermore, missing ArUco observations in video captures halted downstream STL export.
  - **Resolution**: Replaced `mesh.split()` with `trimesh.graph.connected_components(mesh.face_adjacency)` to operate directly on face index arrays, extracting only the target component via `mesh.submesh([target_faces], append=True)` in < 2 seconds using minimal RAM. Implemented dominant component isolation barring any component with < 1,000 faces when large components exist. Implemented graceful ArUco fallback in `ScalingProcessor` preserving photogrammetric units (`scale_factor = 1.0`) when marker is observed in < 2 views. Added `--mesh-only` in `scripts/demo.py` and cached validation results in `StlExporter`. Verified end-to-end on real 1M-face shoe mesh.

- **ISSUE-RES-006: Poisson Zero-Crossing Air Balloons & Attached Floor Planes**
  - **Resolved**: 2026-11-10 (Iteration 018)
  - **Description**: Screened Poisson surface reconstruction with `trim 0` inflated into giant zero-crossing balloons in unobserved airspace above open shoe cavities, while connecting the bottom perimeter to the floor plane. Subsequent hole repair created duplicate candidate triangles across boundary pinch vertices, causing non-manifold edges that failed the manufacturing printability gate.
  - **Resolution**: Implemented KDTree point cloud distance culling (`cull_by_point_cloud_distance`) using $3.5 \times \text{spacing}$ to prune 440,699 ungrounded air faces and detach the floor plane. Implemented horizontal RANSAC floor estimation and planar base slicing (`slice_and_cap_base`) at $Z_{\text{base}}$. Added `split_into_simple_cycles` to eliminate figure-8 pinch vertices and tracked `existing_face_sets` to prevent duplicate non-manifold face generation. Multi-pass defect closure achieved 0 boundary edges, 0 non-manifold edges, and positive volume, passing the printability gate and exporting a 344k-face binary STL.

- **ISSUE-RES-007: STL float32 Quantization Collapse at Millimeter Scale**
  - **Resolved**: 2026-11-10 (Iteration 019)
  - **Description**: Exporting raw photogrammetric models with tiny extents (~2.4 mm) into single-precision float32 binary STL caused 12–14 non-manifold edge collapses when reloaded into slicers due to adjacent micro-vertices snapping to identical 32-bit float values.
  - **Resolution**: Added `--target-length <float>` in `scripts/demo.py` to uniformly scale the cleaned mesh in 64-bit float memory prior to STL export. Evaluated in-memory scaling on real 344k-face shoe to 280.0 mm max extent ($s = 117.18321$), preserving manifold topology, passing the printability gate, and exporting a 17.2 MB STL with volume $269,555.2\,\text{mm}^3$.

- **ISSUE-RES-008: Diagonal Slicing via Arbitrary Photogrammetric Reference Frame**
  - **Resolved**: 2026-11-10 (Iteration 020 / Iteration 021)
  - **Description**: COLMAP reconstructs models in arbitrary camera reference frames where the support plane is tilted (e.g. 28.2°). Slicing along raw horizontal planes cut diagonally across the object, and cutting created tiny boundary floaters that broke watertightness.
  - **Resolution**: Created `CoordinateNormalizer` in `src/loom/geometry/alignment.py` using vectorized RANSAC and Rodrigues $SO(3)$ rotation to align the support plane normal to $[0, 0, 1]^T$ at $Z=0$. Inverted the pipeline handoff in `demo.py` so alignment precedes mesh cleaning. Added boundary floater pruning in `slice_and_cap_base` to discard < 5% slivers, achieving 100% watertight binary STL.

- **ISSUE-RES-009: 25+ Minute Pipeline Bottleneck & Non-Convex Base Triangulation**
  - **Resolved**: 2026-11-10 (Iteration 022)
  - **Description**: Processing unconstrained video through exhaustive matching and double-pass PatchMatch stereo at 1600px produced 25+ minute runtimes and thermal throttling. Furthermore, centroid fan triangulation on non-convex planar sole loops produced overlapping triangles.
  - **Resolution**: Implemented the unified `--turbo` pipeline in `scripts/demo.py`, `ColmapAdapter`, and `VideoConfig`: 36 frames downscaled to 960px max dimension, GPU sequential matching (`overlap=5`, `quadratic_overlap=0`), 16-thread mapper (12/10 BA), single-pass photometric stereo (`window_radius=4`, `num_iterations=3`), Poisson meshing at depth 9 with native normal vectors, and microsecond planar polygon triangulation via `mapbox-earcut` enforcing outward downward normals ($n_z < 0$). Reduced total end-to-end turnaround from 25+ minutes to 151 seconds (2.5 minutes), producing a 100% watertight, printability-gate-verified binary STL.



