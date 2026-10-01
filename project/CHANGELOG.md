# ITERATION CHANGELOG — VIDEO2PRINT

This log records chronological development iterations. Every agent completing meaningful work must add an entry following this format.

---

## Iteration 006 — Phase 2 & Phase 3 Validation, Hardening & Pipeline Handoff Audit
- **Date**: 2026-10-01
- **Milestone**: Phase 2 — Reconstruction Backend Integration (Adapter & Contracts Verified; Host Binary BLOCKED `ISSUE-BLK-002`); Phase 3 — Raw Geometry & Mesh Processing (VERIFIED & AUDITED with 124 total tests)
- **Changes Implemented**:
  - Audited host environment photogrammetry executables: searched system PATH, `C:\`, `C:\Program Files`, `C:\Users\adise`, `AppData`, `tools`. Neither `meshroom_batch.exe` nor `colmap.exe` is present on disk (`ISSUE-BLK-002`). Confirmed NVIDIA GeForce RTX 4060 Laptop GPU with Driver 592.82 and CUDA 13.1 ready for photogrammetry binary installation.
  - Phase 2 live reconstruction status kept explicitly marked `BLOCKED` as mandated by project constitution and completion gates.
  - Hardened `MeshroomAdapter` in `src/loom/reconstruction/meshroom.py`:
    - Updated `parse_camera_sfm` to handle both dictionary and list JSON schemas for `views` and `poses`, calculate pose counts, clamp `registration_ratio` to $[0.0, 1.0]$.
    - Added `.stl` candidate extension to mesh discovery, added fallback to `sfm.json` if `cameras.sfm` is absent.
  - Hardened Phase 3 geometry diagnostics and cleanup:
    - Added configurable `degenerate_area_threshold: float = 1e-7` to `MeshConfig` in `src/loom/config/models.py`.
    - Updated `MeshDiagnostics.inspect()` and `MeshCleaner.clean()` to detect and purge collinear sliver triangles while accounting for float serialization rounding differences between memory and disk representations.
    - Suppressed Trimesh internal `RuntimeWarning: invalid value encountered in divide` on open surfaces by guarding `fix_inversion` with `if mesh.is_watertight:` and `warnings.catch_warnings()`.
  - Hardened pipeline orchestration in `src/loom/pipeline/runner.py`:
    - Added safety try/except wrapper around `MeshProcessor.process` in `run_phase1_pipeline`. When a raw mesh is corrupt or unreadable, sets `mesh_processing_result.status = "FAILED"`, writes `geometry.json`, and cleanly separates reconstruction success from geometry processing failure.
    - Added user warning when `--clean-mesh` is requested with video input without `--reconstruct`.
  - Added photogrammetry raw mesh fixture in `tests/fixtures/mesh_fixtures.py` (`create_photogrammetry_raw_mesh`):
    - Synthesized 1040-triangle sphere dome with 40-edge open base boundary, 3-edge pinhole, 2 floating satellite noise clusters, collinear slivers, duplicate faces, unreferenced vertices, and arbitrary SfM offset coordinates.
    - Saved reference raw mesh fixture to `data/raw/sample_photogrammetry_raw.obj`.
  - Added comprehensive test suites (9 new tests):
    - `tests/unit/mesh/test_photogrammetry_audit.py` (6 unit audit tests verifying diagnostics, component selection, cleanup, conservative hole repair, scale/coordinate preservation, and JSON report generation on realistic photogrammetry mesh).
    - `tests/integration/full_pipeline/test_phase2_phase3_handoff.py` (3 integration tests verifying full Phase 1 $\to$ Phase 2 $\to$ Phase 3 handoff, reconstruction failure skipping Phase 3, and failure discrimination between reconstruction success and corrupt mesh processing failure).
- **Verification**:
  - Full test suite passed: **124 passed in 9.28s** (100% pass rate, 9 new tests + 115 existing tests, zero failures, zero warnings).
  - CLI execution verified: `python -m loom geometry --input data/raw/sample_photogrammetry_raw.obj` executed in 0.0508s, producing `cleaned_sample_photogrammetry_raw.obj` and `reports/geometry.json`.
  - Degraded execution verified: `python -m loom --video data/raw/synthetic_test.mp4 --reconstruct --clean-mesh` completed cleanly with `Status: RECONSTRUCTION BLOCKED (Backend Executable Unavailable on Host)`.
- **Next Step**:
  - Provision external reconstruction tool (`meshroom_batch` or `colmap`) to unblock live photogrammetry (`ISSUE-BLK-002`).
  - Proceed with Phase 4 (Fiducial Metric Scaling & Coordinate Transformation).

---

## Iteration 005 — Phase 3: Raw Geometry & Mesh Processing Implementation & Fixture Validation
- **Date**: 2026-10-01
- **Milestone**: Phase 3 — Raw Geometry & Mesh Processing (IMPLEMENTED & FIXTURE-TESTED with 115 tests; Live Reconstruction: Awaiting Host Binary `ISSUE-BLK-002`)
- **Changes Implemented**:
  - Enforced strict Phase 3 architectural boundaries: zero Phase 4+ functionality added (no metric scaling, no ArUco markers, no absolute dimensions, no CAD ground-truth accuracy benchmarking, no printability analysis, no STL manufacturing export, no neural AI/PyTorch/Depth Anything dependencies). Reconstructed coordinates and physical scale strictly preserved.
  - Installed authorized dependencies: `trimesh==5.1.0` and `scipy==1.15.3` (authorized under `.agents/rules/python.md`). Updated `pyproject.toml`.
  - Implemented typed domain exceptions in `src/loom/mesh/exceptions.py`: `MeshError`, `MeshFormatError`, `MeshInvalidError`, `MeshLoadError`, `MeshProcessingError`.
  - Extended configuration models in `src/loom/config/models.py`: added `component_strategy`, `min_component_faces`, `min_component_ratio`, `remove_degenerate_faces`, `remove_unreferenced_vertices`, `remove_duplicate_faces`, `unify_normals`, `max_hole_edges`, `fill_holes`.
  - Implemented typed data models in `src/loom/mesh/models.py`: `GeometryDiagnostics`, `ComponentInfo`, `ComponentActionResult`, `CleanupActionResult`, `RepairActionResult`, `MeshProcessingResult`, and `MeshProcessingStage` enum.
  - Implemented read-only diagnostics in `src/loom/mesh/diagnostics.py`: vertex/face counts, bounding box, extents, volume, surface area, component count, boundary edges, boundary loops, non-manifold edges/vertices, watertightness, Euler characteristic, NaN/Inf detection, zero-area degenerate triangles, duplicate faces, unreferenced vertices, and status categorization (`VALID`, `WARNING`, `ERROR`).
  - Implemented connected component analysis in `src/loom/mesh/components.py`: `MeshComponentAnalyzer` supporting strategies (`largest`, `largest_by_area`, `min_faces`, `relative_threshold`, `keep_all`) based on face-adjacency graph traversal without external graph packages.
  - Implemented deterministic cleanup in `src/loom/mesh/cleanup.py`: `MeshCleaner` removing NaN/Inf vertices, invalid face indices, zero-area degenerate triangles (cross-product area $\le 10^{-12}$), duplicate faces, and unreferenced vertices.
  - Implemented conservative hole repair in `src/loom/mesh/repair.py`: `MeshRepairer` extracting directed boundary loops, classifying defects by size threshold (`max_hole_edges`), triangulating eligible loops via 2D ear-clipping, honestly preserving complex defects in `defect_details`, and unifiying outward normals via pure NumPy BFS without `networkx`.
  - Implemented pipeline orchestrator in `src/loom/mesh/processor.py`: `MeshProcessor` managing the 8-stage pipeline while strictly preserving coordinate values and physical scale.
  - Implemented standalone runner in `src/loom/pipeline/runner.py`: `run_phase3_mesh_pipeline()` generating `outputs/runs/<run_id>/geometry/cleaned_<stem>.obj` and `reports/geometry.json`.
  - Integrated Phase 3 into CLI (`src/loom/__main__.py`): added `geometry` subcommand (`python -m loom geometry --input <mesh>`) and direct flag (`--mesh`), with structured terminal diagnostic summary.
  - Authored comprehensive Phase 3 specification in `docs/geometry.md`.
  - Constructed deterministic test fixtures in `tests/fixtures/mesh_fixtures.py` (`clean_cube`, `disconnected_mesh`, `degenerate_mesh`, `hole_mesh`, `large_hole_mesh`, `duplicate_and_unreferenced_mesh`).
  - Added 40 new unit and integration tests across `tests/unit/mesh/` and `tests/integration/mesh_pipeline/`.
- **Verification**:
  - Full test suite passed: **115 passed in 7.20s** (100% pass rate, 40 new tests + 75 existing tests, zero regressions).
  - Validated all 4 core fixture types through end-to-end pipeline:
    - `clean_cube`: 8 vertices, 12 faces, 1 component, watertight True, SUCCESS.
    - `disconnected`: 12 -> 8 vertices, 16 -> 12 faces, 2 -> 1 component, watertight True, SUCCESS.
    - `degenerate`: 11 -> 8 vertices, 13 -> 12 faces, zero-area face and unreferenced vertices removed, watertight True, SUCCESS.
    - `hole`: 8 -> 8 vertices, 11 -> 12 faces, boundary loop repaired, watertightness restored, SUCCESS.
  - CLI smoke test verified: `python -m loom geometry --input outputs/experiments/phase3_validation/hole.obj` completed with exit code 0, generated valid intermediate mesh and `reports/geometry.json`.
- **Next Step**:
  - Unblock host photogrammetry backend (`ISSUE-BLK-002`) to run live smartphone video through Phase 1 -> Phase 2 -> Phase 3 end-to-end.
  - Begin Phase 4 (Fiducial Metric Scaling & Coordinate Transformation).

---

## Iteration 004 — Phase 2: Architecture, Contracts, Failure Classification & Pipeline Integration

- **Date**: 2026-09-26
- **Milestone**: Phase 2 — Multi-View 3D Reconstruction Integration (Architecture & Adapter: IMPLEMENTED & VERIFIED with 75 tests; Live execution: BLOCKED pending host binary)
- **Changes Implemented**:
  - Enforced strict Phase 2 architectural boundaries: zero Phase 3+ functionality added (no mesh cleanup, no hole repair, no metric scaling, no ArUco detection, no STL export, no heavyweight AI dependencies).
  - Explicitly decoupled software implementation status from live reconstruction experimental validation status.
  - Defined explicit 7-state failure classification enumeration `ReconstructionStatus` (`SUCCESS`, `PARTIAL`, `BINARY_UNAVAILABLE`, `INVALID_INPUT`, `PROCESS_FAILED`, `TIMEOUT`, `ARTIFACT_MISSING`) in `src/loom/reconstruction/models.py`.
  - Defined 8 conceptual reconstruction stages via `ReconstructionStage` enum (Stage 0: Input Validation, Stage 1: Camera Init, Stage 2: Camera Registration, Stage 3: Sparse Reconstruction, Stage 4: Dense Reconstruction, Stage 5: Raw Meshing, Stage 6: Artifact Discovery, Stage 7: Diagnostics).
  - Expanded `ReconstructionResult` and `ReconstructionArtifact` models with decoupled multi-tier artifacts: `sparse_reconstruction_path`, `dense_point_cloud_path`, `raw_mesh_path`, `workspace_path`, `log_path`, `status`, and backward-compatible alias properties.
  - Extended exception hierarchy in `src/loom/reconstruction/exceptions.py` with `ReconstructionInvalidInputError` (inherits from `ValueError` and `FileNotFoundError` for backward compatibility), `ReconstructionTimeoutError` (inherits from `ReconstructionExecutionError`), and `ReconstructionPartialError`.
  - Hardened `MeshroomAdapter` in `src/loom/reconstruction/meshroom.py`:
    - Implemented `DiscoveredArtifacts` dataclass supporting 3-variable tuple unpacking (`mesh, pc, sfm`), sequence indexing, and dictionary access for 100% backward compatibility.
    - Explicitly distinguished dense point clouds (`densePointCloud.ply`, `pointCloud.ply`) from sparse SfM clouds (`cloud_and_poses.ply`, `sfm.ply`).
    - Handled partial reconstructions (`status=PARTIAL`) where sparse/dense point cloud and camera poses were generated but meshing failed or was not produced.
    - Handled missing artifacts (`status=ARTIFACT_MISSING`) when subprocess returns 0 without writing output files.
    - Attached `reconstruction.log` path to `ReconstructionResult`.
  - Updated `src/loom/pipeline/runner.py` and `reports/reconstruction.json` to write standardized schema containing `status`, `sparse_reconstruction`, `dense_point_cloud_path`, `point_cloud_path`, `workspace_path`, and `log_path`.
  - Enhanced CLI (`src/loom/__main__.py`) terminal summary output to display categorized failure state, sparse SFM cloud, dense point cloud, workspace, and log file paths.
  - Authored comprehensive Phase 2 architectural specification in `docs/reconstruction.md`.
  - Added 10 new tests: unit tests in `tests/unit/reconstruction/test_meshroom_adapter.py` (partial reconstruction, artifact missing, timeout subclass, invalid input error types, discovered artifacts properties, reconstruction stage sequence) and integration tests in `tests/integration/reconstruction/test_reconstruction_contract.py` and `tests/integration/video_pipeline/test_phase1_pipeline.py`.
- **Verification**:
  - Full test suite passed: **75 passed in 5.62s** (100% pass rate, zero regressions across all 75 tests).
  - CLI `--help` and `--dry-run` verified.
  - Synthetic pipeline with `--reconstruct` executed on `data/raw/synthetic_test.mp4`: verified graceful degradation (`BINARY_UNAVAILABLE`), non-crashing execution, valid `reports/reconstruction.json` output, and informative terminal summary.
- **Next Step**:
  - Install Meshroom 2023.3 on development host (or pass `--meshroom-path`) and provide a real smartphone capture to run live 3D reconstruction.

---

## Iteration 003 — Phase 1.5 Verification & Hardening, Phase 2: Meshroom 3D Reconstruction Adapter
- **Date**: 2026-09-26
- **Milestone**: Phase 2 — Multi-View 3D Reconstruction Integration (IMPLEMENTED & VERIFIED with mocked subprocess; Live execution BLOCKED by host binary)
- **Changes Implemented**:
  - Independently verified Phase 1 baseline test suite: exactly 52 tests passed in 3.59s with 0 failures, 0 warnings.
  - Fixed documentation drift across the repository: replaced stale `src/video2print/` references with actual `src/loom/` in `project/ROADMAP.md` and `.agents/rules/architecture.md`.
  - Conducted host environment discovery: searched system PATH, standard Windows program directories, and winget registry. Verified that `meshroom_batch`, `aliceVision_*`, and `colmap` are not installed on the development host (`ISSUE-BLK-002`).
  - Extended configuration models (`src/loom/config/models.py`, `loader.py`, `configs/*.yaml`) to support `binary_path: Optional[Path] = None`, `keep_workspace: bool = True`, and `additional_args: list[str]`.
  - Extended result models (`src/loom/reconstruction/models.py`) with `mesh_path`, `point_cloud_path`, `camera_poses_path`, `input_frames_count`, `registered_cameras_count`, `registration_ratio`, `point_count`, `error_message`, and `backend` alias.
  - Implemented typed reconstruction exceptions in `src/loom/reconstruction/exceptions.py`: `ReconstructionError`, `ReconstructionBinaryNotFoundError`, `ReconstructionExecutionError`, `ReconstructionArtifactNotFoundError`.
  - Implemented production `MeshroomAdapter` in `src/loom/reconstruction/meshroom.py`:
    - `resolve_binary()` and `is_available()` checking configuration overrides, environment variables (`MESHROOM_PATH`, `MESHROOM_BIN`), and system PATH.
    - CLI argument construction (`build_command()`) without shell invocation (`shell=False`).
    - AliceVision `cameras.sfm` JSON parser extracting registered camera count and registration ratio.
    - Multi-tier output artifact discovery (`discover_output_artifacts()`) locating `texturedMesh.obj/ply`, `mesh.obj/ply`, `cloud_and_poses.ply`, and `cameras.sfm`.
    - Isolated workspace layout (`outputs/runs/<run_id>/reconstruction/workspace/{input,output,cache,logs}`).
    - Subprocess execution using safe `proc.communicate(timeout=...)` with streaming log capture into `reconstruction.log`.
  - Implemented `ReconstructionRunner` in `src/loom/reconstruction/runner.py` with factory lookup and descriptive error for unsupported backends.
  - Integrated reconstruction into the pipeline runner (`src/loom/pipeline/runner.py`), directly feeding Phase 1 selected keyframes to the reconstruction adapter and generating `reports/reconstruction.json`.
  - Extended CLI (`src/loom/__main__.py`) with `--reconstruct` and `--meshroom-path` flags and comprehensive Phase 2 summary terminal output.
  - Created smartphone capture guide in `docs/capture/capture_guide.md` specifying physical target requirements, lighting, orbital trajectory (two elevation rings), and overlap requirements.
  - Created standalone diagnostic smoke test script in `scripts/reconstruction_smoke_test.py`.
  - Implemented 13 unit tests with mocked subprocess in `tests/unit/reconstruction/test_meshroom_adapter.py` testing missing binary, invalid inputs, command construction, SFM parsing, artifact discovery, successful runs, non-zero return codes, timeouts, and missing mesh failure reporting.
- **Verification**:
  - Full test suite passed: **65 passed in 4.60s** (13 new reconstruction tests + 52 existing tests, 100% pass rate).
  - CLI dry-run verified: `python -m loom --dry-run` passed.
  - CLI Phase 1 verified: `python -m loom --video data/raw/synthetic_test.mp4` passed.
  - CLI Phase 2 graceful degradation verified: `python -m loom --video data/raw/synthetic_test.mp4 --reconstruct` correctly reported missing binary, generated valid `reconstruction.json`, and displayed structured Phase 2 terminal summary.
- **Next Step**:
  - Install Meshroom 2023.3 on development host (or pass `--meshroom-path`) and provide a real smartphone capture to run live 3D reconstruction.

---

## Iteration 002 — Phase 1: Video Ingest, Frame Extraction & Capture Quality
- **Date**: 2026-09-26
- **Milestone**: Phase 1 — Video Ingest, Frame Extraction & Capture Quality (COMPLETED)
- **Changes Implemented**:
  - Installed and pinned Phase 1 dependencies in Python 3.10.11 `.venv`: `numpy==2.2.6`, `opencv-python==5.0.0.93`, `tqdm==4.70.1`.
  - Implemented OpenCV-based video validation and container metadata extraction in `src/loom/video/metadata.py` with robust duration calculation, stream property validation, FourCC decoding, and deterministic `try...finally: cap.release()`.
  - Implemented `VideoIngestor` in `src/loom/video/ingest.py`, validating container formats and producing verified `VideoArtifact`.
  - Implemented sequential streaming frame extraction in `src/loom/video/frames.py` with configurable sampling interval, target FPS, max_frames, JPEG quality encoding, deterministic filenames (`frame_{idx:06d}.jpg`), and machine-readable `manifest.json`. Zero whole-video RAM retention.
  - Implemented deterministic optical quality analysis in `src/loom/capture/quality.py`:
    - Sharpness via Laplacian variance on grayscale images.
    - Brightness via grayscale mean (with configurable min/max exposure rejection).
    - Contrast via grayscale standard deviation (with configurable min contrast threshold).
    - Redundancy filtering via 64x64 thumbnail mean absolute difference against previous accepted frame (`redundancy_threshold=0.98`).
  - Implemented 2D viewpoint diversity estimation in `src/loom/capture/coverage.py` and actionable capture guidance generation in `src/loom/capture/guidance.py`.
  - Implemented Phase 1 pipeline execution in `src/loom/pipeline/runner.py` with standardized output directory structure (`outputs/runs/<run_id>/frames/{raw,selected}`, `reports/{metadata.json,capture_analysis.json}`, `logs/pipeline.log`).
  - Extended CLI (`src/loom/__main__.py`) supporting `--video`, `--config`, `--output-dir`, and outputting rich terminal execution summaries.
  - Completed synthetic test video generator `scripts/generate_test_video.py` producing controlled variations (normal, blurred, dark, bright, redundant frames).
  - Built comprehensive unit tests (`test_metadata.py`, `test_frames.py`, `test_quality.py`) and end-to-end integration tests (`test_phase1_pipeline.py`).
- **Verification**:
  - `pytest tests/ -v` passed all 52 tests (100% pass rate).
  - Synthetic video generation tested: 60 frames @ 30 FPS, 640x480 generated and verified.
  - CLI execution verified: `python -m loom --video data/raw/synthetic_test.mp4` successfully ran end-to-end, extracted 60 frames, filtered defects, copied 5 high-quality keyframes to `frames/selected/`, and generated both JSON reports and log file.
  - Memory & resource safety verified: streaming extraction consumes constant minimal memory (< 80 MB) without accumulative memory growth.
- **Next Step**:
  - Phase 2 Planning: Multi-View 3D Reconstruction Integration (Meshroom / AliceVision CLI adapter).

---

## Iteration 001 — Complete Application Scaffold & Test Hierarchy
- **Date**: 2026-09-26
- **Milestone**: Phase 0 — Application Scaffold & Architecture
- **Changes Implemented**:
  - Installed Python 3.10.11 64-bit on host via winget and activated virtual environment `.venv/` resolving `ISSUE-BLK-001`.
  - Created standard src-layout package `src/loom/` with `pyproject.toml` supporting `python -m loom` CLI.
  - Implemented typed configuration system (`src/loom/config/`) with YAML parser and preset profiles (`configs/default.yaml`, `configs/development.yaml`, `configs/experiment.yaml`).
  - Implemented immutable artifact model (`src/loom/pipeline/artifacts.py`) and pipeline stage contracts (`src/loom/pipeline/stages.py`, `src/loom/pipeline/runner.py`) supporting dry-run verification.
  - Implemented 3D geometric math models (`src/loom/geometry/`) including `Point3D`, `Vector3D`, `BoundingBox3D`, and `TransformMatrix4x4`.
  - Scaffolded interfaces and data contracts across all pipeline stages:
    - `src/loom/video/`: VideoIngestor, VideoMetadata, FrameExtractor (streaming contract)
    - `src/loom/capture/`: FrameQualityAssessor, CoverageEstimator, CaptureGuidance
    - `src/loom/reconstruction/`: ReconstructionEngine ABC, MeshroomAdapter, ColmapAdapter, ReconstructionRunner
    - `src/loom/pointcloud/`: PointCloudCleaner, PointCloudFilter, PointCloudAnalyzer
    - `src/loom/mesh/`: MeshCleaner, MeshRepairer, MeshTopologyAnalyzer, SurfaceReconstructor
    - `src/loom/scaling/`: ArucoDetector, ScaleCalibrator, ScaleTransformer
    - `src/loom/validation/`: DimensionAnalyzer, GeometryComparator, GroundTruthComparison, ValidationReportGenerator
    - `src/loom/printability/`: ManifoldChecker, WatertightChecker, WallThicknessAnalyzer, OverhangAnalyzer, PrintabilityReportGenerator
    - `src/loom/export/`: StlExporter, ExportManifest, ExportReportGenerator
    - `src/loom/utils/`: logging, paths, subprocess, hashing
  - Created test suite hierarchy under `tests/` with 35 unit and integration tests across package imports, configs, artifacts, runner dry-run, geometry math, and stage contracts.
  - Created utility and diagnostic scripts under `scripts/`: `environment_check.py`, `generate_test_video.py`, `generate_marker.py`, `benchmark.py`.
  - Created directory scaffolding for `data/`, `outputs/`, and `docs/` with `.gitkeep` placeholders.
  - Authored architecture overview documentation in `docs/architecture/overview.md`.
  - Updated `README.md` to clearly distinguish Implemented, Scaffolded, and Planned subsystems.
  - Updated `project/CONTEXT.md` and `project/ISSUES.md` (resolved `ISSUE-BLK-001`).
- **Verification**:
  - `python -m loom --help`, `python -m loom --dry-run`, and `python -m loom -c configs/default.yaml --dry-run` execute cleanly.
  - `pytest tests/ -v` passes 35 out of 35 tests with 0 failures and 0 warnings.
  - `scripts/environment_check.py` successfully diagnoses runtime and dependency status.
  - Verified no circular imports, no fake photogrammetry/meshing logic, and proper `NotImplementedError` boundaries on scaffolded interfaces.
- **Next Step**:
  - Phase 1 Kickoff: Implement real streaming video ingest, frame extraction, and Laplacian sharpness quality filtering using OpenCV.

---

## Iteration 000 — Project Bootstrap & Agent Operating System
- **Date**: 2026-09-26
- **Milestone**: Phase 0 — Project Bootstrap
- **Changes Implemented**:
  - Inspected repository state (clean git working tree on branch `main`, Python 3.10.11 registered in `py` launcher but binary missing on disk; active host Python is 3.14.7).
  - Created project constitution [`AGENTS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/AGENTS.md) with core directives, mandatory iteration workflow, and context update protocols.
  - Created architectural rules in [`.agents/rules/architecture.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/architecture.md) detailing pipeline stages, interfaces, and backend replaceability.
  - Created Python standards in [`.agents/rules/python.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/python.md) specifying Python 3.10.11 runtime, lean dependency policy, and logging/path conventions.
  - Created 3D reconstruction rules in [`.agents/rules/reconstruction.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/reconstruction.md) detailing subprocess adapter pattern, monocular scale ambiguity, and ArUco marker scaling.
  - Created testing philosophy in [`.agents/rules/testing.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/testing.md) establishing independent testability and synthetic test fixtures.
  - Created research integrity rules in [`.agents/rules/research.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/research.md) enforcing zero fabrication of measurements or results.
  - Created current state snapshot in [`project/CONTEXT.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/CONTEXT.md).
  - Created 11-phase staged development plan in [`project/ROADMAP.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/ROADMAP.md).
  - Documented four initial Architecture Decision Records in [`project/DECISIONS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/DECISIONS.md) (ADR-001 through ADR-004).
  - Established schema and empirical logging rules in [`project/EXPERIMENTS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/EXPERIMENTS.md).
  - Recorded initial discoveries, limitations, and research questions in [`project/ISSUES.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/ISSUES.md).
- **Verification**:
  - Validated all 12 project governance and rule files created.
  - Verified no implementation code was falsely marked complete.
  - Verified internal consistency across rules, roadmap, ADRs, and issues.
- **Next Step**:
  - Begin Phase 1: Initialize `.venv` with Python 3.10.11, pin core dependencies in `requirements.txt`, and implement video ingest / frame extraction module with unit tests.
