# ARCHITECTURE DECISION RECORDS (ADR) — VIDEO2PRINT

This document records the architectural and engineering decisions accepted for VIDEO2PRINT. Every entry follows the ADR specification.

---

## ADR Index

- [ADR-001: Standardization on Python 3.10.11 Runtime](#adr-001-standardization-on-python-31011-runtime)
- [ADR-002: Selection of Meshroom / AliceVision CLI as Initial Reconstruction Backend](#adr-002-selection-of-meshroom--alicevision-cli-as-initial-reconstruction-backend)
- [ADR-003: Subprocess Isolation and Adapter Pattern for External Reconstruction Tools](#adr-003-subprocess-isolation-and-adapter-pattern-for-external-reconstruction-tools)
- [ADR-004: Known-Size Reference Marker (ArUco) for Development Metric Scaling](#adr-004-known-size-reference-marker-aruco-for-development-metric-scaling)
- [ADR-005: Deterministic Optical Quality Assessment and Thumbnail Redundancy Filtering](#adr-005-deterministic-optical-quality-assessment-and-thumbnail-redundancy-filtering)
- [ADR-006: Meshroom Subprocess Execution, Timeout Safety, and Artifact Discovery Architecture](#adr-006-meshroom-subprocess-execution-timeout-safety-and-artifact-discovery-architecture)
- [ADR-007: Explicit Reconstruction Failure Classification and Decoupled Multi-Tier Artifact Model](#adr-007-explicit-reconstruction-failure-classification-and-decoupled-multi-tier-artifact-model)
- [ADR-008: Conservative Defect Repair and Graph-Engine Independence in Mesh Processing](#adr-008-conservative-defect-repair-and-graph-engine-independence-in-mesh-processing)
- [ADR-009: Coordinate Value and Physical Scale Preservation During Mesh Cleanup & Normalization](#adr-009-coordinate-value-and-physical-scale-preservation-during-mesh-cleanup--normalization)

---


## ADR-001: Standardization on Python 3.10.11 Runtime

- **Status**: ACCEPTED
- **Date**: 2026-09-26
- **Decision**: Adopt Python 3.10.11 as the designated baseline execution environment for the project.
- **Reason**:
  - Python 3.10 provides optimal binary wheel compatibility across critical 3D geometry and computer vision libraries (`open3d`, `pymeshlab`, `trimesh`, `opencv-python`).
  - Newer Python releases (e.g. Python 3.12, 3.13, 3.14) frequently lack pre-compiled wheels for C++-bound geometry tools like `pymeshlab` and `open3d` on Windows.
  - Python 3.10.11 is verified to be installed on the development host system (`py -3.10`).
- **Alternatives Considered**:
  - *Python 3.14 (Default host Python)*: Incompatible; scientific and 3D mesh processing wheels are largely unavailable.
  - *Python 3.8 / 3.9*: Older syntax, end-of-life or approaching end-of-life status.
- **Consequences**:
  - Virtual environments must be created explicitly using `py -3.10 -m venv .venv`.
  - Agents must avoid Python 3.11+ exclusive features (e.g., `except*`, `Self` from typing without typing-extensions).

---

## ADR-002: Selection of Meshroom / AliceVision CLI as Initial Reconstruction Backend

- **Status**: ACCEPTED
- **Date**: 2026-09-26
- **Decision**: Use Meshroom / AliceVision CLI as the primary initial external photogrammetry engine.
- **Reason**:
  - AliceVision provides an open-source, reproducible Structure-from-Motion (SfM) and Multi-View Stereo (MVS) pipeline.
  - Meshroom provides straightforward command-line workflow automation (`meshroom_batch` / individual AliceVision node binaries).
  - It handles feature extraction, camera estimation, depth map generation, and mesh reconstruction without requiring custom SfM implementations.
- **Alternatives Considered**:
  - *Custom SfM/MVS implementation*: Rejected. Writing robust multi-view stereo and bundle adjustment from scratch would consume the entire semester without matching production reliability.
  - *COLMAP + OpenMVS*: Excellent alternative, but Meshroom was chosen as the starting point due to its unified CLI packaging. COLMAP will be supported as a subsequent interchangeable backend.
  - *NeRF / 3D Gaussian Splatting*: Premature and non-standard for CAD/3D printing. Meshing from radiance fields remains noisy and lacks geometric/metric precision compared to classical MVS.
- **Consequences**:
  - Dense depth mapping requires an NVIDIA GPU with CUDA.
  - The software must be installed as an external tool, and the pipeline must handle cases where the tool is missing or fails.

---

## ADR-003: Subprocess Isolation and Adapter Pattern for External Reconstruction Tools

- **Status**: ACCEPTED
- **Date**: 2026-09-26
- **Decision**: Isolate all external reconstruction binaries behind an abstract `ReconstructionEngine` interface invoked exclusively through managed subprocesses.
- **Reason**:
  - Prevents tight coupling between the core VIDEO2PRINT application and external toolchain quirks.
  - Enables switching or adding backends (e.g. COLMAP, OpenMVS) with zero modifications to upstream frame selection or downstream mesh cleaning, scaling, and validation.
  - Subprocess isolation protects the Python runtime from C++ native crashes or memory leaks in photogrammetry engines.
- **Alternatives Considered**:
  - *Direct Python C-bindings (e.g., pycolmap)*: Introduces delicate compilation dependencies and platform-specific build issues on Windows.
  - *Hardcoding Meshroom file structures into the core pipeline*: Severely violates modularity and makes backend switching nearly impossible.
- **Consequences**:
  - Data transfer occurs via filesystem artifacts (directories of images, `.obj` / `.ply` files).
  - Overhead of process launching and file I/O is negligible compared to photogrammetry computation time.

---

## ADR-004: Known-Size Reference Marker (ArUco) for Development Metric Scaling

- **Status**: ACCEPTED
- **Date**: 2026-09-26
- **Decision**: Use a known-size physical fiducial marker (ArUco marker or ArUco grid board) placed beside or beneath the target object to establish absolute metric scale.
- **Reason**:
  - Monocular Structure-from-Motion has intrinsic gauge freedom (scale ambiguity); absolute real-world size cannot be determined from uncalibrated 2D video frames alone.
  - ArUco markers can be detected with sub-pixel corner accuracy using `opencv-python`.
  - Calculating scale from known millimeter marker dimensions ($s = \frac{d_{\text{physical}}}{d_{\text{reconstructed}}}$) is deterministic, verifiable, and does not require active depth sensors (LiDAR/ToF).
- **Alternatives Considered**:
  - *Smartphone LiDAR / ARKit / ARCore scale*: Device-dependent (requires high-end iPhone Pro or specific Android phones) and limits accessibility.
  - *Manual scale factor input*: Subjective, error-prone, and fails the requirement for automated manufacturing readiness.
  - *Object-bounding-box prior*: Unreliable for arbitrary organic or unfamiliar mechanical shapes.
- **Consequences**:
  - Capture protocol during development requires the user to place an ArUco marker in the scene alongside the target object.
  - The marker geometry must later be segmented out or trimmed from the final printable object mesh if it contacts the object.

---

## ADR-005: Deterministic Optical Quality Assessment and Thumbnail Redundancy Filtering

- **Status**: ACCEPTED
- **Date**: 2026-09-26
- **Decision**: Adopt Laplacian variance for blur detection, grayscale mean/standard deviation for exposure/contrast validation, and 64x64 grayscale thumbnail mean absolute difference for inter-frame redundancy filtering.
- **Reason**:
  - Computational efficiency: These metrics require basic matrix operations via NumPy and OpenCV, executing in milliseconds per frame without GPU requirements or neural network dependencies.
  - Determinism: Given identical frame input, the quality scoring and accept/reject decisions are 100% reproducible.
  - Redundancy filtering prevents feeding hundreds of static or near-static consecutive frames into photogrammetry, which would explode bundle adjustment computation time without increasing geometric reconstruction quality.
  - A 64x64 normalized thumbnail captures overall scene composition and viewpoint shifts while being insensitive to high-frequency sensor noise.
- **Alternatives Considered**:
  - *Optical Flow (Lucas-Kanade / Farneback)*: Accurate but substantially slower for long 4K/1080p video sequences. Deferred to later optimization phases if simple difference metrics prove insufficient on difficult footage.
  - *Deep learning quality models (e.g., BRISQUE, KonIQ, NIMA)*: Heavyweight dependencies (PyTorch/TensorFlow) violating Phase 1 dependency rules, non-deterministic across devices, and unnecessary for basic blur/exposure gating.
- **Consequences**:
  - Default thresholds (`sharpness_threshold=100.0`, `min_brightness=30.0`, `max_brightness=235.0`, `min_contrast=15.0`, `redundancy_threshold=0.98`) provide robust initial filtering but remain fully user-configurable via `CaptureConfig` for challenging lighting environments.

---

## ADR-006: Meshroom Subprocess Execution, Timeout Safety, and Artifact Discovery Architecture

- **Status**: ACCEPTED
- **Date**: 2026-09-26
- **Decision**: Execute Meshroom (`meshroom_batch`) via isolated subprocess with explicit argument lists (`shell=False`), safe timeout handling via `proc.communicate(timeout=...)`, streaming stdout/stderr into `reconstruction.log`, native JSON parsing of AliceVision's `cameras.sfm` for camera registration metrics, and controlled multi-tier output discovery for 3D meshes.
- **Reason**:
  - `shell=False` eliminates command injection vulnerabilities and path escaping issues across Windows and POSIX systems.
  - Photogrammetry can hang or exceed reasonable compute budgets on degenerate captures; timeout enforcement with process termination and cleanup is mandatory.
  - AliceVision produces structured `cameras.sfm` files containing `"views"` and `"poses"`; parsing this allows computing objective camera registration ratios ($R = \frac{|\text{poses}|}{|\text{views}|}$) without heuristics or fabrication.
  - Meshroom's exact output path varies between versions and pipeline node graphs (`texturedMesh.obj`, `texturedMesh.ply`, `MeshFiltering/mesh.obj`); multi-tier discovery with explicit priority avoids brittle hardcoded paths while failing deterministically if no non-empty mesh is produced.
- **Alternatives Considered**:
  - *Hardcoded output path (`workspace/output/texturedMesh.obj`)*: Brittle; fails if Meshroom version exports PLY or writes to intermediate cache nodes.
  - *Unbounded subprocess execution without timeout*: Unsafe; could lock system resources indefinitely on low-feature captures.
- **Consequences**:
  - Output discovery checks direct paths, then cached node outputs, prioritizing textured meshes over untextured intermediate meshes.
  - If Meshroom exits 0 but produces no valid 3D mesh artifact, the adapter marks `success=False` with a descriptive message rather than claiming success.

---

## ADR-007: Explicit Reconstruction Failure Classification and Decoupled Multi-Tier Artifact Model

- **Status**: ACCEPTED
- **Date**: 2026-09-26
- **Decision**: Define a 7-state enumeration (`ReconstructionStatus`: `SUCCESS`, `PARTIAL`, `BINARY_UNAVAILABLE`, `INVALID_INPUT`, `PROCESS_FAILED`, `TIMEOUT`, `ARTIFACT_MISSING`) and decoupled artifact model separating sparse reconstruction (`sparse_reconstruction_path`), dense point cloud (`dense_point_cloud_path`), and raw surface mesh (`mesh_path`). Standardize `reports/reconstruction.json` to reflect this classification.
- **Reason**:
  - Photogrammetry pipelines frequently complete initial stages (feature extraction, camera registration, sparse/dense point cloud triangulation) while failing downstream surface meshing due to memory exhaustion, planar degeneracies, or noise.
  - Collapsing partial reconstructions into a generic failure discards valuable diagnostic artifacts and prevents future recovery strategies.
  - Collapsing missing host executables into generic runtime crashes breaks user trust and prevents automated fallback or helpful installation instructions.
  - Distinguishing sparse SfM clouds from dense MVS clouds prevents downstream stages from misinterpreting a sparse point cloud as a dense printable surface.
- **Alternatives Considered**:
  - *Binary boolean success flag only*: Masks root causes; inability to distinguish missing binary from algorithm convergence failure or partial completion.
  - *Unified point cloud path without sparse/dense distinction*: Causes ambiguity in point density and downstream filtering parameters.
- **Consequences**:
  - Downstream pipeline stages and CLI summary outputs explicitly inspect `status` and can access partial artifacts when available.
  - When the photogrammetry backend is not installed on the host system, the pipeline completes Phase 1 successfully, gracefully logs `BINARY_UNAVAILABLE`, and outputs a valid `reconstruction.json` without crashing.

---

## ADR-008: Conservative Defect Repair and Graph-Engine Independence in Mesh Processing

- **Status**: ACCEPTED
- **Date**: 2026-10-01
- **Decision**: Implement conservative boundary defect repair using pure NumPy edge uniqueness, 2D ear-clipping triangulation, and BFS normal/winding propagation, without relying on external networkx graph packages or AI mesh infilling tools.
- **Reason**:
  - In photogrammetry, real reconstructed surfaces may legitimately feature open boundaries (e.g. uncaptured bases or flat supporting tables). Blindly filling all holes deforms authentic geometry.
  - Standard Trimesh convenience methods (`fill_holes`, `fix_winding`, `split`) conditionally invoke `networkx.cycle_basis`, which fails if optional graph dependencies are absent.
  - Pure NumPy edge analysis and breadth-first winding propagation runs deterministically in milliseconds, eliminates library fragility, and respects user-configured edge thresholds (`max_hole_edges`).
  - Ineligible holes ($> \text{max\_hole\_edges}$) are honestly logged as preserved defects in `defect_details` rather than triggering hidden geometry deformation.
- **Alternatives Considered**:
  - *Blind automatic hole filling (`trimesh.repair.fill_holes`)*: Distorts genuine geometry on large complex contours and requires networkx.
  - *Poisson surface reconstruction for all inputs*: Blurs sharp mechanical edges, closes genuine openings indiscriminately, and introduces high computational overhead.
  - *Neural AI inpainting (e.g., Point-E, NeRF-based mesh completion)*: Prohibited by `.agents/rules/python.md`; non-deterministic and computationally excessive.
- **Consequences**:
  - Small, simple holes ($\le 30$ edges) are cleanly closed, restoring watertightness on reparable geometries.
  - Large or open boundary loops are safely preserved and transparently reported in `reports/geometry.json`.

---

## ADR-009: Coordinate Value and Physical Scale Preservation During Mesh Cleanup & Normalization

- **Status**: ACCEPTED
- **Date**: 2026-10-01
- **Decision**: Strictly preserve original vertex coordinate positions and coordinate scale throughout Phase 3 mesh processing, prohibiting origin recentering, bounding box normalization, or unit scaling until Phase 4 (Metric Scaling).
- **Reason**:
  - Photogrammetric reconstruction backends produce 3D geometry in an arbitrary coordinate frame where camera positions, fiducial reference markers, and object surfaces share a common metric or relative scale.
  - Normalizing mesh size to a unit cube or translating bounding box minimum to origin (`(0, 0, 0)`) breaks camera pose correspondence and destroys the spatial relationship needed to detect and measure fiducial reference markers (ArUco) in Phase 4.
  - Physical scale interpretation is strictly reserved for Phase 4.
- **Alternatives Considered**:
  - *Auto-centering mesh bounding box at origin*: Destroys world coordinate alignment with photogrammetric SfM camera coordinates.
  - *Normalizing vertices to $[-1, 1]$ unit sphere/cube*: Premature scale alteration that makes downstream physical measurement impossible.
- **Consequences**:
  - Mesh normalization in Phase 3 is purely representational: re-indexing vertex arrays, removing degenerate/duplicate faces, and orienting outward normals.
  - Surviving vertex positions remain exactly identical in their native coordinate frame.



