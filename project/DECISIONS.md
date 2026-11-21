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
- [ADR-010: COLMAP CUDA Dense Stereo Pipeline and Safe Meshing Fallback Policy](#adr-010-colmap-cuda-dense-stereo-pipeline-and-safe-meshing-fallback-policy)
- [ADR-011: RANSAC Floor Plane Removal, Centroid Proximity Selection, and Pure NumPy Base Capping](#adr-011-ransac-floor-plane-removal-centroid-proximity-selection-and-pure-numpy-base-capping)
- [ADR-012: 2D-to-3D ArUco Triangulation and Affine Metric Scaling](#adr-012-2d-to-3d-aruco-triangulation-and-affine-metric-scaling)
- [ADR-013: Oriented Bounding Box Measurement, Manufacturing Printability Gate, and Validated Binary STL Export](#adr-013-oriented-bounding-box-measurement-manufacturing-printability-gate-and-validated-binary-stl-export)
- [ADR-014: Sequential Video Feature Matching and Multi-Threaded Mapper Scaling for COLMAP](#adr-014-sequential-video-feature-matching-and-multi-threaded-mapper-scaling-for-colmap)
- [ADR-015: Dense Stereo Fusion Point Density Boost & Dense Delaunay Mesher Fallback](#adr-015-dense-stereo-fusion-point-density-boost--dense-delaunay-mesher-fallback)
- [ADR-016: Memory-Safe Connected Components, Dominant Component Isolation, and ArUco Graceful Fallback](#adr-016-memory-safe-connected-components-dominant-component-isolation-and-aruco-graceful-fallback)
- [ADR-017: KDTree Point Cloud Distance Culling, Planar Base Slicing, and Watertight Loop Closure](#adr-017-kdtree-point-cloud-distance-culling-planar-base-slicing-and-watertight-loop-closure)
- [ADR-018: In-Memory Target-Length Scaling Prior to Binary STL Export](#adr-018-in-memory-target-length-scaling-prior-to-binary-stl-export)
- [ADR-019: Canonical Coordinate Frame Normalization via RANSAC Support Plane Alignment](#adr-019-canonical-coordinate-frame-normalization-via-ransac-support-plane-alignment)
- [ADR-020: Canonical Alignment Pre-Cleaning Handoff & Post-Slice Floater Pruning](#adr-020-canonical-alignment-pre-cleaning-handoff--post-slice-floater-pruning)
- [ADR-021: Unified Turbo Video-to-3D-Print Pipeline (< 200s Total Runtime)](#adr-021-unified-turbo-video-to-3d-print-pipeline--200s-total-runtime)
- [ADR-022: Pre-Mesh Canonical Normalization, Normal Vector Rotation, and Sub-Millimeter Depth 10 Poisson Meshing](#adr-022-pre-mesh-canonical-normalization-normal-vector-rotation-and-sub-millimeter-depth-10-poisson-meshing)
- [ADR-023: Robust Production Photogrammetry Engine (SfM Circuit Breaker, Upward Gravity Camera Polarity, Anti-Starburst Topology Guards, and Turbo Settings)](#adr-023-robust-production-photogrammetry-engine-sfm-circuit-breaker-upward-gravity-camera-polarity-anti-starburst-topology-guards-and-turbo-settings)

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

---

## ADR-010: COLMAP CUDA Dense Stereo Pipeline and Safe Meshing Fallback Policy

- **Status**: ACCEPTED
- **Date**: 2026-11-09
- **Decision**: Implement a 4-stage sequential dense Multi-View Stereo (MVS) pipeline in `ColmapAdapter` (`image_undistorter` -> `patch_match_stereo` -> `stereo_fusion` -> `poisson_mesher`) with enforced CUDA stereo buffer safeguards (`--PatchMatchStereo.gpu_index 0`, `--PatchMatchStereo.max_image_size 1600`, `--PatchMatchStereo.window_radius 5`, `--PatchMatchStereo.num_iterations 5`, `--PatchMatchStereo.geom_consistency true`). Enforce explicit opt-in for sparse Delaunay meshing (`--allow-sparse-fallback`), strictly banning silent fallbacks to sparse wireframe Delaunay meshing on dense failure.
- **Reason**:
  - Dense MVS produces dense, watertight Poisson surfaces suitable for 3D printing, whereas sparse Delaunay meshing produces an untextured wireframe mesh unsuitable for manufacturing.
  - Silent fallback from failed dense reconstruction to sparse Delaunay corrupts downstream metric scaling and printability analysis while masking photogrammetry failures.
  - Setting `--PatchMatchStereo.max_image_size 1600` safeguards 8 GB GPU VRAM (e.g. RTX 4060) against out-of-memory errors.
- **Alternatives Considered**:
  - *Automatic fallback to Delaunay meshing on dense error*: Rejected; masks failures and delivers broken wireframes to users requesting dense meshes.
  - *Direct subprocess calls from script/demo.py*: Rejected; violates modular architecture rules requiring all photogrammetry backends to sit behind `ReconstructionEngine` adapters.
- **Consequences**:
  - `ColmapAdapter` encapsulates all COLMAP CLI execution and argument construction.
  - `demo.py` and downstream pipelines receive typed artifacts (`ColmapDenseArtifact`) pointing directly to `meshed-poisson.ply`.
  - Dense reconstruction failures raise explicit `ReconstructionError`.

---

## ADR-011: RANSAC Floor Plane Removal, Centroid Proximity Selection, and Pure NumPy Base Capping

- **Status**: ACCEPTED
- **Date**: 2026-11-09
- **Decision**:
  1. Implement normal-constrained horizontal RANSAC floor detection ($|\mathbf{n} \cdot \mathbf{e}_z| \ge \cos(20^\circ)$) restricted to the lower bounding box percentile ($Z \le Z_{\min} + 0.15 \Delta Z$) and centroid proximity component selection.
  2. Implement planar base capping via pure NumPy triangle slicing and 2D ear-clipping loop triangulation, strictly avoiding external `shapely` dependencies.
  3. Export intermediate checkpoint meshes `04_floor_removed.ply` and `05_base_capped.ply`.
- **Reason**:
  - Naive face-count component filtering fails when floor or wall clutter has more faces than the target object, and unconstrained plane RANSAC risks shearing angled shoe soles.
  - Photogrammetric scanning cannot view underneath a resting object, leaving ragged or open bottoms unsuited for build-plate contact. Slicing at $Z_{\text{base}}$ and capping creates a planar outsole contact surface for 3D printing.
  - Pure NumPy implementation eliminates dependencies on `shapely` or external C extensions, preserving zero-heavy-dependency architecture.
- **Alternatives Considered**:
  - *`trimesh.intersections.slice_mesh_plane`*: Rejected due to mandatory external dependency on `shapely`.
  - *Unconstrained RANSAC plane deletion*: Rejected because arbitrary angled cuts shear legitimate shoe geometry.
- **Consequences**:
  - Capped meshes achieve complete watertightness at the base while strictly preserving upper object geometry.
  - Intermediate checkpoints `04_floor_removed.ply` and `05_base_capped.ply` provide visibility into pre-print geometry preparation.

---

## ADR-012: Multi-View DLT ArUco Triangulation and Affine Matrix Scaling

- **Status**: ACCEPTED
- **Date**: 2026-11-09
- **Decision**:
  1. Map 2D ArUco corner observations into COLMAP's 3D coordinate system using Direct Linear Transformation (DLT via SVD) with multi-view RANSAC outlier ray rejection ($> 2.0$ px error threshold).
  2. Parse COLMAP `cameras.bin` / `cameras.txt` and `images.bin` / `images.txt` directly to extract intrinsics ($K$), lens distortion, and camera poses ($R, \mathbf{t}$), undistorting marker corners where necessary.
  3. Reconstruct 3D Euclidean distances between perimeter marker corners ($L_{\text{sfm}}$) and derive metric scale factor $s = L_{\text{real (mm)}} / L_{\text{sfm}}$.
  4. Apply 4x4 affine transformation matrix ($v' = s \cdot v$) to mesh vertices, logging target marker size, reconstructed SfM size, and calculated scale factor.
- **Reason**:
  - 2D pixel coordinates cannot directly scale 3D meshes without knowing camera geometry and depth. Multi-view triangulation bridges 2D detections into metric photogrammetric reality.
  - Multi-view RANSAC consensus protects the 3D marker coordinates from grazing-angle or distorted corner detections exceeding 2.0 px reprojection error.
  - Affine matrix formulation provides mathematically rigorous vertex transformation while strictly preserving face topology, indexing, and normal consistency.
- **Alternatives Considered**:
  - *Single-view PnP pose estimation*: Rejected; highly sensitive to camera focal length drift and 2D pixel jitter across individual frames.
  - *Manual scale input*: Kept as fallback, but automatic 2D-to-3D triangulation enables hands-free pipeline execution.
- **Consequences**:
  - `ArucoDetector` automatically infers $L_{\text{sfm}}$ from COLMAP outputs.
  - `ScalingProcessor` automatically scales raw or cleaned meshes to real-world millimeters.

---

## ADR-013: Oriented Bounding Box Measurement, Manufacturing Printability Gate, and Validated Binary STL Export

- **Status**: ACCEPTED
- **Date**: 2026-11-09
- **Decision**:
  1. Implement Oriented Bounding Box (OBB) principal dimension calculation ($L \ge W \ge H$ in millimeters) using convex-hull oriented bounds with pure NumPy PCA covariance fallback to handle planar/degenerate geometry without `networkx`.
  2. Implement manufacturing readiness printability gate enforcing:
     - Watertightness: closed 2-manifold with boundary edges == 0.
     - 2-manifold surface: non-manifold edges == 0 and non-manifold pinched vertices == 0.
     - Positive volume: volume > 0.0 $mm^3$.
  3. Export binary STL files (`outputs/stl/<model_name>_metric.stl`) and serialize provenance JSON build manifests containing bounding box dimensions, volume ($mm^3$), triangle count, and SHA-256 hash.
- **Reason**:
  - Manufacturing readiness requires strict topological and geometric integrity. 3D slicers (Cura, PrusaSlicer, Bambu Studio) fail or produce slicing artifacts on open boundaries or non-manifold junctions.
  - Slicers need principal dimensions ($L, W, H$) and build volume to verify fit on printer build plates.
  - Binary STL format is the universal standard for 3D additive manufacturing.
- **Alternatives Considered**:
  - *Export without validation gate*: Rejected; risks delivering unprintable meshes with open bottom surfaces or inverted normals.
  - *Relying on external libraries (`networkx`, `shapely`)*: Rejected; pure NumPy BFS and PCA keeps zero heavy dependencies.
- **Consequences**:
  - Invalid meshes are blocked before export with descriptive diagnostic error messages.
  - Slicer-ready binary STL models and machine-readable manifests are generated reliably.

---

## ADR-014: Sequential Video Feature Matching and Multi-Threaded Mapper Scaling for COLMAP

- **Status**: ACCEPTED
- **Date**: 2026-11-09
- **Decision**:
  1. For video input captures or when sequential matching is requested, replace $O(N^2)$ exhaustive matching with `colmap sequential_matcher`:
     - `--SequentialMatching.overlap 10`
     - `--SequentialMatching.quadratic_overlap 1`
     - `--SequentialMatching.loop_detection 1`
     - `--FeatureMatching.use_gpu 1`
     - `--FeatureMatching.gpu_index 0`
  2. Scale CPU Mapper execution to 16 threads (`--Mapper.num_threads 16`) to fully saturate host CPU cores (e.g. Ryzen 7 7840HS 16-thread architecture).
  3. Cap global Bundle Adjustment iterations (`--Mapper.ba_global_max_num_iterations 20`) to eliminate diminishing-returns BA cycles and reduce sparse SfM processing turnaround from 25+ minutes to under 2 minutes.
  4. Reduce default video extraction limit (`--max-frames`) in demo runner from 300 to 80 frames.
- **Reason**:
  - Video frames exhibit high temporal locality; matching all $N(N-1)/2$ image pairs is wasteful and leads to exponential computation scaling.
  - Sequential matching with quadratic overlap and vocabulary-tree loop detection preserves full trajectory tracking and loop closure while reducing match comparisons by >85%.
  - Default COLMAP single-threaded or unconstrained BA mapping leads to long waits with negligible accuracy gain after 20 iterations.
- **Alternatives Considered**:
  - *Exhaustive matching with high frame skips*: Fails to maintain parallax overlap across tight turns and wastes time on distant frame pairs.
  - *Vocab tree matching only*: Lacks temporal ordering guarantees needed for smooth video SfM.
- **Consequences**:
  - Sparse SfM turnaround accelerates drastically from 25+ minutes to under 2 minutes.
  - Robustness on orbital smartphone video capture is maintained with loop closure.

---

## ADR-015: Dense Stereo Fusion Point Density Boost & Dense Delaunay Mesher Fallback

- **Status**: ACCEPTED
- **Date**: 2026-11-09
- **Decision**:
  1. Configure `colmap stereo_fusion` with:
     - `--StereoFusion.min_num_pixels 2` (default 5 culled over 80% of points in small-baseline video captures).
     - `--StereoFusion.max_image_size 1600` (safeguards 8 GB VRAM buffer).
  2. Configure `colmap poisson_mesher` with:
     - `--PoissonMeshing.depth 10` (octree maximum resolution).
     - `--PoissonMeshing.trim 0` (default 10 pruned 100% of triangles on sparse boundary regions, resulting in 248-byte empty files with 0 vertices).
     - `--PoissonMeshing.point_weight 1.0` (preserves surface adherence to fused point cloud).
  3. Implement automatic dense Delaunay meshing fallback:
     - After running Poisson mesher, inspect vertex count via `read_ply_vertex_count(poisson_ply)`.
     - If vertices == 0 or if Poisson meshing exits with an error/timeout, trigger fallback to `colmap delaunay_mesher --input_type dense --input_path <dense_workspace> --output_path <dense_workspace>/meshed-delaunay.ply`.
     - Return valid mesh pointing to the Delaunay mesh, populating `delaunay_mesh_path` on `ColmapDenseArtifact`.
- **Reason**:
  - COLMAP Poisson Mesher uses Kazhdan's screened Poisson formulation with an optional SurfaceTrimmer post-pass (`--PoissonMeshing.trim`). In photogrammetry where baseline coverage is localized (e.g. smartphone orbital scans of a shoe), default trim threshold 10 purges low-density octree leaf nodes, frequently deleting 100% of the surface and yielding an empty 248-byte PLY file.
  - Setting `--PoissonMeshing.trim 0` disables this deletion, guaranteeing that generated octree surfaces remain intact.
  - If Poisson mesher still fails due to degenerate normals or extreme sparsity, dense Delaunay mesher constructs tetrahedral visibility meshes directly from the dense point cloud, guaranteeing a watertight 2-manifold raw mesh for Phase 3 cleaning and capping.
- **Alternatives Considered**:
  - *Sparse Delaunay fallback*: Produces poor wireframe meshes that lack surface detail.
  - *Increasing point density threshold without changing trim*: SurfaceTrimmer still pruned valid boundary faces even with 50,000+ points.
- **Consequences**:
  - Solves the empty Poisson mesh crash (`Mesh file contains no geometry`).
  - Stereo fusion point yields increase significantly (> 2x points retained).
  - Guarantees valid non-empty geometry output for Phase 3 mesh repair and Phase 7 STL manufacturing.

---

## ADR-016: Memory-Safe Connected Components, Dominant Component Isolation, and ArUco Graceful Fallback

- **Status**: ACCEPTED
- **Date**: 2026-11-10
- **Decision**:
  1. Replace `mesh.split(only_watertight=False)` in `MeshComponentAnalyzer` and `MeshCleaner` with `trimesh.graph.connected_components(mesh.face_adjacency)` to compute sorted face index arrays directly without allocating redundant `Trimesh` objects. Extract only the single selected component using `mesh.submesh([target_faces], append=True)`.
  2. Implement dominant component isolation logic:
     - Identify components with > 100,000 faces (or > 20% of total faces and >= 1,000 faces for models with >= 10,000 faces).
     - Component #0 is the primary object (the shoe).
     - Under NO circumstances should any component with < 1,000 faces be chosen as the target object when large components exist.
     - When `reference_point` is None, default directly to Component #0.
  3. Implement graceful ArUco fallback:
     - If physical marker ID 0 is observed in < 2 registered camera frames, catch `ReferenceDetectionError`, log a warning, preserve photogrammetric units (`scale_factor = 1.0`), and proceed smoothly to printability gates and STL export.
  4. Register `--mesh-only` in `scripts/demo.py` to allow direct execution of Phases 3–7 on pre-existing mesh files, bypassing video ingest and COLMAP SfM/MVS.
  5. Cache printability validation result in `StlExporter` to eliminate redundant evaluations when falling back with `enforce_gate=False`.
- **Reason**:
  - `mesh.split()` instantiated hundreds of separate `Trimesh` objects for noise fragments, consuming ~7 GB RAM and causing Linux kernel OOM kills on 1M-face photogrammetric reconstructions.
  - Centroid distance calculation using whole-mesh bounding box centers inadvertently selected a 122-face noise speck and discarded the 1.03M-face shoe.
  - ArUco marker occlusions in video captures previously aborted the entire reconstruction and export pipeline.
- **Alternatives Considered**:
  - *Increasing host swap*: Mitigates OOM symptoms without solving the underlying exponential memory allocation.
  - *Hardcoding Component #0 unconditionally*: Breaks scene isolation where user provides an explicit target reference coordinate.
- **Consequences**:
  - Eliminates kernel OOM kills and reduces memory overhead from ~7 GB to < 100 MB.
  - Guarantees preservation of the primary shoe component (> 1,000,000 faces).
  - Enables standalone testing of downstream meshing, repair, and STL export via `--mesh-only`.

---

## ADR-017: KDTree Point Cloud Distance Culling, Planar Base Slicing, and Watertight Loop Closure

- **Status**: ACCEPTED
- **Date**: 2026-11-10
- **Decision**:
  1. **KDTree Point Cloud Distance Culling**:
     - Construct a `scipy.spatial.cKDTree` on the dense MVS point cloud (`fused.ply`).
     - Estimate local point spacing using median 2-NN distance across a deterministic random sample of points.
     - Cull any reconstructed Poisson mesh face whose vertices exceed $3.5 \times \text{spacing}$ from the nearest point cloud point.
     - Discards Poisson zero-crossing air balloons in unobserved regions while naturally detaching horizontal floor skirts from the target object.
  2. **Planar Base Slicing & Capping**:
     - Implement `MeshCleaner.fit_floor_plane_ransac` to estimate horizontal floor plane equation.
     - Implement `MeshRepairer.slice_and_cap_base`: slice mesh at $Z_{\text{base}} = Z_{\text{min}} + \text{percentile} \cdot \Delta Z$, perturbing slice elevation if vertices lie within $1e-6$ to prevent zero-length cut segments.
     - Close open underside boundary loops with downward-facing triangles ($\mathbf{n} = (0, 0, -1)$).
  3. **Non-Manifold Loop Decomposition & Multi-Pass Closure**:
     - Implement `split_into_simple_cycles` to break complex figure-8 / pinch-vertex loops into disjoint simple cycles without duplicate vertices.
     - Track `existing_face_sets: set[frozenset[int]]` during hole triangulation to strictly prevent duplicate faces and non-manifold edges.
     - Wrap hole extraction in a multi-pass loop when `close_all_holes` is enabled to resolve touching boundary loops.
     - Enforce vertex merging when loading STL files to reconstruct edge adjacency and face topology.
     - Sequence `MeshProcessor.process` to execute base capping before defect repair so remaining perimeter gaps are cleanly sealed.
- **Reason**:
  - Running Poisson meshing with `trim 0` created unobserved air surface balloons extending into empty space, while connecting the shoe to the surrounding floor plane.
  - Previous ear-clipping hole closure generated duplicate faces on boundary pinch vertices, causing non-manifold edges and failing the printability gate.
  - STL files loaded with `process=False` had unmerged coincident vertices, preventing topological manifold detection.
- **Alternatives Considered**:
  - *Aggressive Poisson trimming (`trim 10`)*: Re-introduces the empty mesh defect where 100% of real geometry is culled.
  - *External boolean cutting libraries (`shapely`, `blender`, `cgal`)*: Violates project zero-heavy-dependency directive (ADR-001, ADR-008).
- **Consequences**:
  - Reconstructed meshes pass the manufacturing printability gate with 0 open boundary edges, 0 non-manifold edges, and 0 non-manifold vertices.
  - Validated binary STL and JSON manifest exports are generated deterministically in < 15 seconds.

---

## ADR-018: In-Memory Target-Length Scaling Prior to Binary STL Export

- **Status**: ACCEPTED
- **Date**: 2026-11-10
- **Decision**:
  - Introduce `--target-length <float>` in `scripts/demo.py` CLI to allow specifying a physical target maximum dimension in millimeters (e.g. 280.0 mm for footwear).
  - When fiducial ArUco metric scaling is skipped or unobserved, and `--target-length` is provided:
    1. Compute scale factor $s = \text{target\_length} / \max(\text{mesh.extents})$ from the cleaned photogrammetric mesh.
    2. Apply `mesh.apply_scale(s)` in 64-bit floating point memory before file serialization.
    3. Re-run `mesh.merge_vertices()` and `mesh.fix_normals()`.
    4. Pass the scaled `Trimesh` object directly to `StlExporter`.
- **Reason**:
  - The standard binary STL format specifies IEEE 754 single-precision (float32) vertex coordinates with ~7 decimal digits of precision.
  - When small raw photogrammetric models (~2.4 mm extents) with dense micro-triangles (edge lengths $< 10^{-4}$ mm) are exported directly to float32 STL, adjacent vertex coordinates snap together, causing 12–14 non-manifold edge collapses upon file reloading.
  - Scaling uniformly to physical millimeters (e.g. 280 mm) in 64-bit float memory prior to export separates vertex coordinates by orders of magnitude, eliminating float32 quantization collapse.
- **Alternatives Considered**:
  - *Exporting to OBJ or PLY only*: Bypasses standard 3D slicer compatibility requirements (slicers expect binary STL).
  - *Post-export STL repair*: Downstream triangle mesh repair tools may degrade geometric sharpness. Scaling upstream in float64 is mathematically lossless.
- **Consequences**:
  - Preserves manifold topology and watertightness throughout binary STL export and 3D slicer ingestion.
  - Real-world footwear dimensions (280.0 mm max extent, $269,555.2\,\text{mm}^3$ volume) are directly exportable without manual slicer scaling.

---

## ADR-019: Canonical Coordinate Frame Normalization via RANSAC Support Plane Alignment

- **Status**: ACCEPTED
- **Date**: 2026-11-10
- **Decision**:
  - Implement Phase 4 Canonical Frame Normalization in `src/loom/geometry/alignment.py` via `CoordinateNormalizer`.
  - Use vectorized RANSAC plane fitting with adaptive distance thresholds ($0.015 \cdot \text{bbox\_diag}$) to isolate the dominant support surface.
  - Enforce normal polarity pointing toward the non-plane object mass center so the canonical vertical vector points upward away from the support surface.
  - Compute the $SO(3)$ Rodrigues rotation mapping the support normal to $[0, 0, 1]^T$, translate the support surface to $Z = 0$, and center the subject geometry at $(X = 0, Y = 0)$.
  - Support input geometries across `np.ndarray`, `trimesh.PointCloud`, and `trimesh.Trimesh`.
- **Reason**:
  - Photogrammetric SfM/MVS reconstructs scene points in an arbitrary camera reference frame where the physical ground or table plane is arbitrarily tilted.
  - Slicing or capping base geometry using raw axis-aligned cut planes ($Z = \text{const}$) cuts diagonally through the subject unless the support plane is canonically aligned to the horizontal plane.
- **Alternatives Considered**:
  - *PCA-based alignment*: Bounding box eigenvectors do not correspond to the physical ground plane when the object is asymmetric or irregular.
  - *Manual orientation GUI*: Incompatible with automated headless batch processing pipelines.
- **Consequences**:
  - Downstream planar base slicing cuts precisely parallel to the physical contact surface.
  - 3D models rest flat on the $(Z = 0)$ print bed, centered at $(X = 0, Y = 0)$, matching 3D printing build plate conventions.

---

## ADR-022: Pre-Mesh Canonical Normalization, Normal Vector Rotation, and Sub-Millimeter Depth 10 Poisson Meshing

- **Status**: ACCEPTED
- **Date**: 2026-11-10
- **Decision**:
  - Perform canonical support plane normalization and foreground cylindrical cropping directly on the dense point cloud (`dense/fused.ply`) *before* meshing.
  - Implement binary little-endian PLY reading and writing (`read_ply_with_normals`, `write_ply_with_normals`) preserving exact float32 coordinates (`x, y, z`), unit normal vectors (`nx, ny, nz`), and colors (`red, green, blue`).
  - Rotate normal vectors in lockstep with vertex coordinates: $\mathbf{n}_{\text{new}} = \mathbf{n} R^T$ for $R \in SO(3)$.
  - Prune subsurface points ($Z < -0.005$) and background clutter beyond $R_{\text{cut}} = 1.25 \times R_{98}$ from the elevated center of mass.
  - Call `/usr/bin/colmap poisson_mesher` on `dense/fused_isolated.ply` with `--PoissonMeshing.depth 10`, `--PoissonMeshing.point_weight 1.0`, `--PoissonMeshing.trim 0`.
  - Slice bottom perimeter at $Z = 0.0051$ and cap with `mapbox-earcut` ($n_z < 0$).
  - Enforce in-memory float64 uniform scaling to `--target-length` and snap sole flush to $Z = 0.0$ (`mesh.vertices[:, 2] -= mesh.bounds[0][2]`).
- **Reason**:
  - Running Poisson meshing on raw scenes containing background walls and furniture causes the solver to bridge the object to background clutter or balloon into unobserved air.
  - Running Poisson meshing at depth 9 causes feature smoothing (potato meshes); depth 10 preserves fine texture, laces, and contours while executing in ~12 seconds on the isolated point cloud.
  - Preserving native rotated normals (`nx, ny, nz`) in `fused_isolated.ply` prevents `colmap poisson_mesher` from failing with `Ply file does not contain normals` and eliminates slow Delaunay fallbacks.
  - Meshing an already canonically leveled point cloud guarantees that the resulting mesh is upright and parallel to the printer build plate.
- **Alternatives Considered**:
  - *Post-mesh plane fitting*: Closed meshes without a ground table surface cause RANSAC to lock onto angled sidewalls, tilting the mesh.
  - *Trimesh PLY export*: Strips normal vector properties, crashing COLMAP's native PoissonRecon parser.
- **Consequences**:
  - `colmap poisson_mesher` executes directly in ~12 seconds with 312,897 vertices.
  - Produces a 100% watertight 2-manifold binary STL with zero non-manifold edges, positive volume, and a perfectly flat contact base snapped to $Z = 0.0$.

---

## ADR-023: Robust Production Photogrammetry Engine (SfM Circuit Breaker, Upward Gravity Camera Polarity, Anti-Starburst Topology Guards, and Turbo Settings)

- **Status**: ACCEPTED
- **Date**: 2026-11-12
- **Decision**:
  - Implement an SfM tracking Circuit Breaker: inspect registered views in `images.bin` / `images.txt` after sparse reconstruction; if registered view count $< 75\%$ of extracted keyframes, abort immediately with `RuntimeError("SfM tracking lost: insufficient overlap or texture. Aborting to prevent invalid geometry.")`.
  - Enforce Upward Gravity Polarity using camera trajectory centroid $\mathbf{C}_{\text{cam}}$: for plane point $\mathbf{p}_0 = -d \cdot \mathbf{n}$, if $\mathbf{n} \cdot (\mathbf{C}_{\text{cam}} - \mathbf{p}_0) < 0 \implies \mathbf{n} = -\mathbf{n}, d = -d$.
  - Implement Anti-Starburst Hole Guard: in `MeshRepairer.repair()`, reject hole filling for any boundary loop containing $> 60$ edges.
  - Standardize Turbo defaults: 68 keyframes @ 960px resolution, Laplacian blur threshold $\tau = 18.0$, sequential matching (`overlap 10`, `quadratic_overlap 1`, `loop_detection 1`), dense MVS (`window_radius 4`, `num_iter 3`, `geom_consistency False`, `StereoFusion.min_num_pixels 3`), cylindrical crop $R_{\text{cut}} = 1.30 \times R_{98}$, and default target length 200.0 mm with $Z_{\min} = 0.000000$ mm flush bed snap.
- **Reason**:
  - Sparse camera tracking drops (e.g. from orbit drift or insufficient overlap) yield open 2.5D surfaces; proceeding with dense meshing generates degenerate starburst triangle fans bridging empty space.
  - Verifying the support plane normal points directly into the camera hemisphere prevents inverted upside-down models regardless of camera tilt or table reflections.
  - Limiting hole-filling to small planar defects ($\le 60$ edges) prevents fan-triangulation across real object apertures (like shoe collars).
- **Alternatives Considered**:
  - *Blind hole filling (`trimesh.repair.fill_holes`)*: Fills open scan boundaries with giant starburst fans that distort real geometry.
  - *Continuing when SfM drops views*: Leads to unprintable fragmented half-meshes.
- **Consequences**:
  - Fails fast on bad or untextured capture videos before wasting GPU compute.
  - Guarantees 100% watertight 2-manifold output when input videos satisfy tracking requirements.















