# STAGED PROJECT ROADMAP — VIDEO2PRINT

This document outlines the sequential, staged roadmap for VIDEO2PRINT. Phases are designed with strict prerequisites and objective, measurable completion criteria. No speculative dates are assigned.

---

## Roadmap Overview

```
Phase 0 ──> Phase 1 ──> Phase 2 ──> Phase 3 ──> Phase 4
[Bootstrap]  [Frames]    [Reconstruct] [Mesh Clean] [Scale]
                                                       │
Phase 10 <── Phase 9 <── Phase 8 <── Phase 7 <── Phase 6 <── Phase 5
[Final Demo] [Physical]  [Benchmarks]  [Guidance] [Printable] [Validate]
```

---

## Phase Details

### Phase 0: Project Bootstrap & Engineering Governance
- **Status**: COMPLETE
- **Objective**: Establish project constitution, architectural rules, engineering standards, and agent operational protocol.
- **Prerequisites**: Clean git repository, Python 3.10 host runtime.
- **Expected Deliverables**:
  - `AGENTS.md` operating constitution.
  - `.agents/rules/` rule set (architecture, python, reconstruction, testing, research).
  - `project/` documentation system (`CONTEXT.md`, `ROADMAP.md`, `DECISIONS.md`, `EXPERIMENTS.md`, `ISSUES.md`, `CHANGELOG.md`).
- **Measurable Completion Criteria**:
  - All governance files exist and are mutually consistent.
  - Context update protocol defined and testable by any subsequent agent.

---

### Phase 1: Reliable Video & Frame Processing Pipeline
- **Status**: COMPLETE
- **Objective**: Build a robust, deterministic video ingest and keyframe selection module.
- **Prerequisites**: Phase 0 complete; `.venv` configured with Python 3.10.11; `opencv-python`, `numpy`, `tqdm` installed.
- **Delivered**:
  - `src/loom/video/metadata.py`: Robust container metadata parsing and duration estimation.
  - `src/loom/video/ingest.py`: File validation and `VideoArtifact` generation.
  - `src/loom/video/frames.py`: Streaming sequential frame extraction, configurable sampling interval, max frames, JPEG quality, and `manifest.json`.
  - `src/loom/capture/quality.py`: Deterministic Laplacian variance sharpness, grayscale mean brightness, grayscale std contrast, and 64x64 thumbnail redundancy filtering.
  - `src/loom/capture/coverage.py` & `guidance.py`: Viewpoint diversity scoring and actionable user feedback notes.
  - `src/loom/pipeline/runner.py`: Phase 1 orchestration writing `frames/{raw,selected}`, `reports/{metadata.json,capture_analysis.json}`, and `logs/pipeline.log`.
  - CLI `python -m loom --video <path>` with concise summary terminal output.
  - `scripts/generate_test_video.py`: Synthetic test video generator.
  - 52 passing tests covering all unit and integration behaviors.
- **Measurable Completion Criteria Verified**:
  - Successfully ingests and extracts frames from video without loading entire video into memory.
  - Blurry, underexposed, overexposed, low contrast, and redundant frames demonstrably filtered.
  - Generates machine-readable `manifest.json`, `metadata.json`, and `capture_analysis.json`.
  - 100% of unit and integration tests pass with zero warnings.

---

### Phase 2: Reconstruction Backend Integration
- **Status**: ARCHITECTURE & ADAPTER IMPLEMENTED / VERIFIED (Live Reconstruction BLOCKED)
- **Objective**: Integrate external photogrammetry engine via an abstract adapter interface, supporting deterministic workspace isolation, robust failure classifications, and typed output artifacts.
- **Prerequisites**: Phase 1 complete; Meshroom / AliceVision binaries configured or mocked for CI.
- **Delivered**:
  - `src/loom/reconstruction/meshroom.py`: Production `MeshroomAdapter` implementing argument construction, workspace isolation (`workspace/{input,output,cache,logs}`), safe timeout handling via `proc.communicate`, real-time stdout/stderr logging to `reconstruction.log`, AliceVision `cameras.sfm` JSON parsing (`registered_cameras_count`, `registration_ratio`), multi-tier output artifact discovery separating dense (`densePointCloud.ply`) and sparse (`cloud_and_poses.ply`) clouds, and backwards-compatible tuple/dict unpacking.
  - `src/loom/reconstruction/models.py`: `ReconstructionStatus` (7 explicit states: `SUCCESS`, `PARTIAL`, `BINARY_UNAVAILABLE`, `INVALID_INPUT`, `PROCESS_FAILED`, `TIMEOUT`, `ARTIFACT_MISSING`), `ReconstructionStage` (8 conceptual pipeline stages), and comprehensive `ReconstructionResult`.
  - `src/loom/reconstruction/exceptions.py`: Typed hierarchy (`ReconstructionInvalidInputError`, `ReconstructionBinaryNotFoundError`, `ReconstructionExecutionError`, `ReconstructionTimeoutError`, `ReconstructionArtifactNotFoundError`, `ReconstructionPartialError`).
  - `src/loom/reconstruction/runner.py`: `ReconstructionRunner` engine factory and job runner.
  - `src/loom/pipeline/runner.py`: End-to-end integration accepting `--reconstruct`, invoking the adapter on Phase 1 selected frames, writing `reports/reconstruction.json`, and providing graceful degradation if the backend executable is absent.
  - `src/loom/__main__.py`: CLI extended with `--reconstruct` and `--meshroom-path` flags, rich Phase 2 summary output with detailed failure state reporting.
  - `docs/reconstruction.md`: Comprehensive Phase 2 architectural specification, contracts, stage definitions, and failure taxonomies.
  - `docs/capture/capture_guide.md`: Standard physical capture protocol for real smartphone videos.
  - `scripts/reconstruction_smoke_test.py`: Standalone environment diagnostic and live smoke test runner.
  - 19 unit tests in `tests/unit/reconstruction/test_meshroom_adapter.py` and integration tests covering the complete Phase 2 contract (75 total passing tests).
- **Measurable Completion Criteria**:
  - [x] Abstract adapter contract (`ReconstructionEngine`) decoupling LOOM from Meshroom internals.
  - [x] Adapter builds execution command, manages isolated workspace directories, executes subprocess securely, and returns typed `ReconstructionResult`.
  - [x] Gracefully handles missing binary (`BINARY_UNAVAILABLE`), invalid input frames (`INVALID_INPUT`), timeouts (`TIMEOUT`), non-zero process exits (`PROCESS_FAILED`), partial reconstructions (`PARTIAL`), and missing artifacts (`ARTIFACT_MISSING`).
  - [x] Discovers and separates output artifacts (dense cloud, sparse cloud, camera poses, raw mesh).
  - [x] Generates standardized machine-readable `reports/reconstruction.json`.
  - [x] Integrated into Phase 1 pipeline with graceful degradation when photogrammetry backend is not installed on the host.
  - [ ] Live reconstruction of real physical object with Meshroom (BLOCKED: `meshroom_batch` not installed on development host; see `ISSUE-BLK-002`).

---

### Phase 3: Raw Geometry Processing & Mesh Cleanup
- **Status**: IMPLEMENTED / FIXTURE-TESTED (Live Reconstruction: Awaiting Host Photogrammetry Backend)
- **Objective**: Clean and repair raw photogrammetric output meshes, producing a verified, normalized intermediate mesh and machine-readable geometry report while strictly preserving physical scale and coordinates.
- **Prerequisites**: Phase 2 complete (or deterministic raw mesh fixtures available).
- **Delivered**:
  - `src/loom/mesh/models.py`: Typed data models and diagnostic reporting structures (`GeometryDiagnostics`, `ComponentInfo`, `ComponentActionResult`, `CleanupActionResult`, `RepairActionResult`, `MeshProcessingResult`, and `MeshProcessingStage` enum).
  - `src/loom/mesh/diagnostics.py`: Comprehensive read-only geometry and topology analysis (vertex/face counts, bounding box, extents, volume, surface area, boundary loops, non-manifold edges, NaN/Inf detection, zero-area degenerate triangles, duplicate faces, unreferenced vertices, Euler characteristic, status categorization: `VALID`, `WARNING`, `ERROR`).
  - `src/loom/mesh/components.py`: Disconnected component analyzer and configurable filtering strategies (`largest`, `largest_by_area`, `min_faces`, `relative_threshold`, `keep_all`) based on face-adjacency graph traversal.
  - `src/loom/mesh/cleanup.py`: Deterministic invalid and degenerate geometry cleanup (NaN/Inf vertex purge, out-of-bounds face index removal, zero-area triangle purge via cross-product area, duplicate face removal, unreferenced vertex removal).
  - `src/loom/mesh/repair.py`: Conservative hole and defect repair using directed boundary loop extraction, 2D-projected ear-clipping triangulation for eligible defects ($\le \text{max\_hole\_edges}$), honest preservation and logging of complex/ineligible defects, and BFS outward normal/winding unification.
  - `src/loom/mesh/processor.py`: Orchestrator executing the 8-stage mesh processing pipeline with coordinate and physical scale preservation (reserving all scaling for Phase 4).
  - `src/loom/pipeline/runner.py`: Standalone execution via `run_phase3_mesh_pipeline()` generating `outputs/runs/<run_id>/geometry/cleaned_<stem>.obj` and `reports/geometry.json`.
  - `src/loom/__main__.py`: CLI geometry subcommand (`python -m loom geometry --input <mesh>`) and direct flag (`--mesh`), with structured terminal diagnostic summary.
  - `tests/fixtures/mesh_fixtures.py`: Deterministic programmatic mesh fixtures (`clean_cube`, `disconnected_mesh`, `degenerate_mesh`, `hole_mesh`, `large_hole_mesh`, `duplicate_and_unreferenced_mesh`, `create_photogrammetry_raw_mesh`).
  - `data/raw/sample_photogrammetry_raw.obj`: Reference photogrammetric raw mesh with realistic defect profile (open base, pinhole, satellite noise clusters, collinear slivers, duplicate faces, unreferenced vertices).
  - `tests/unit/mesh/test_photogrammetry_audit.py`: 6 photogrammetry audit tests verifying diagnostics, component selection, cleanup, conservative hole repair, scale/coordinate preservation, and JSON report generation.
  - `tests/integration/full_pipeline/test_phase2_phase3_handoff.py`: 3 end-to-end integration tests verifying full Phase 1 $\to$ 2 $\to$ 3 handoff, graceful skip on reconstruction failure, and clean failure discrimination on corrupt meshes.
  - `docs/geometry.md`: Comprehensive Phase 3 specification, boundary definitions, and format contracts.
  - 49 unit and integration tests covering all Phase 3 modules and handoffs (124 total tests passing repository-wide).
- **Measurable Completion Criteria**:
  - [x] Read-only diagnostics accurately computed before and after processing without geometry deformation.
  - [x] Multi-component meshes filtered according to configurable strategy (`largest`, `min_faces`, etc.) with transparent removed component tracking.
  - [x] Degenerate zero-area triangles, invalid face indices, and unreferenced vertices deterministically removed.
  - [x] Eligible boundary holes ($\le \text{max\_hole\_edges}$) closed and watertightness restored; complex holes ($> \text{max\_hole\_edges}$) honestly preserved and reported.
  - [x] Coordinate values and physical scale strictly preserved (no translation, no unit rescaling).
  - [x] Machine-readable `reports/geometry.json` generated in standard run hierarchy.
  - [x] CLI execution tested and verified (`python -m loom geometry --input ...`).
  - [x] Realistic photogrammetric defect profile audited and verified without destructive geometry loss.
  - [x] Phase 2 $\to$ Phase 3 automated pipeline handoff and failure discrimination verified.
  - [ ] Live end-to-end validation on live Meshroom-produced photogrammetric mesh (Awaiting host photogrammetry backend `ISSUE-BLK-002`).


---

### Phase 4: Metric Scaling Subsystem
- **Status**: NOT STARTED
- **Objective**: Overcome monocular scale ambiguity by detecting physical fiducial markers and scaling the mesh to real-world millimeters.
- **Prerequisites**: Phase 3 complete; `opencv-python` (ArUco module) and sample frames with known markers.
- **Expected Deliverables**:
  - `src/loom/scaling/`: Fiducial detector (ArUco / reference board), 3D plane/point distance estimator, scale factor calculator ($s = d_{\text{physical}} / d_{\text{reconstructed}}$), and transformation matrix applicator.
  - Unit tests in `tests/unit/test_metric_scaling.py`.
- **Measurable Completion Criteria**:
  - Given an unscaled mesh with a known 50.0 mm ArUco marker, correctly scales the mesh geometry so that the reference marker measures $50.0 \pm 1.0\text{ mm}$ in mesh coordinate space.

---

### Phase 5: Geometry Validation
- **Status**: NOT STARTED
- **Objective**: Quantitatively compare reconstructed mesh geometry against known physical ground-truth dimensions and reference CAD geometry.
- **Prerequisites**: Phase 4 complete; reference geometric test object (e.g. 50mm gauge cube).
- **Expected Deliverables**:
  - `src/loom/validation/`: Bounding box calculator, cross-sectional caliper measurement simulator, Hausdorff distance calculator (mesh-to-mesh / point-to-mesh).
  - Validation reporting module generating structured JSON/Markdown reports.
- **Measurable Completion Criteria**:
  - Computes exact dimensional error (absolute $\Delta\text{ mm}$ and percentage error) against ground truth.
  - Generates reproducible validation artifacts.

---

### Phase 6: Printability Analysis & Slicing Preparation
- **Status**: NOT STARTED
- **Objective**: Automatically verify manufacturing readiness for additive fabrication (FDM/SLA).
- **Prerequisites**: Phase 5 complete; `trimesh` geometry utilities.
- **Expected Deliverables**:
  - `src/loom/printability/`: Watertightness checker (is_watertight), non-manifold edge detector, minimum wall thickness checker, overhang angle analyzer ($> 45^\circ$).
  - `src/loom/export/`: Binary STL exporter with optimal build orientation recommendation.
- **Measurable Completion Criteria**:
  - Successfully detects non-manifold edges or open holes in flawed test meshes.
  - Successfully exports clean, watertight models to standard binary `.stl` format verified readable by standard slicers.

---

### Phase 7: Capture-Quality Assessment & Adaptive Guidance
- **Status**: NOT STARTED
- **Objective**: Provide feedback on whether the smartphone video provides sufficient angular coverage and texture for a reliable reconstruction.
- **Prerequisites**: Phase 1 and Phase 2 complete.
- **Expected Deliverables**:
  - Visual coverage estimation (view sphere sampling around the object bounding box).
  - Incomplete coverage detection (e.g., missing top or back views).
  - Actionable feedback generator ("Slow down video pan", "Increase lighting", "Capture top hemisphere").
- **Measurable Completion Criteria**:
  - Identifies deficient capture trajectories (< 180° orbit or high motion blur) before expensive 3D reconstruction begins.

---

### Phase 8: Baseline Comparison & Benchmark Experiments
- **Status**: NOT STARTED
- **Objective**: Run systematic, documented experiments comparing the full pipeline against baselines.
- **Prerequisites**: Phases 1–6 functional.
- **Expected Deliverables**:
  - Standardized benchmark dataset (3 test objects with calibrated caliper measurements).
  - Logged entries in `project/EXPERIMENTS.md` with zero fabricated values.
  - Comparison against baseline naive photogrammetry (raw video frames without selection/cleanup).
- **Measurable Completion Criteria**:
  - Documented quantitative results showing dimensional error, mesh completeness, and processing duration across multiple real-world capture sessions.

---

### Phase 9: Physical 3D Print Validation
- **Status**: NOT STARTED
- **Objective**: Physically fabricate the generated STL on an FDM/SLA 3D printer and measure dimensional fidelity with digital calipers.
- **Prerequisites**: Phase 6 and Phase 8 complete; physical 3D printer access.
- **Expected Deliverables**:
  - Physical print logs (slicer settings, layer height, infill, filament type).
  - Physical measurement comparison table: Original Object vs. Reconstructed Mesh vs. Physical 3D Printed Part.
- **Measurable Completion Criteria**:
  - Complete end-to-end transition: Physical Object → Smartphone Video → STL → Physical 3D Print.
  - Caliper measurements recorded and analyzed for shrinkage, tolerance, and fidelity.

---

### Phase 10: Final Engineering Demo, Technical Documentation & Research Report
- **Status**: NOT STARTED
- **Objective**: Package the software, documentation, research findings, and demonstration into a cohesive, peer-review quality engineering report.
- **Prerequisites**: All preceding phases complete.
- **Expected Deliverables**:
  - Comprehensive engineering/research report with reproducible methodology.
  - Clean CLI entrypoint (`python -m loom --video input.mp4 --output-dir ./output`).
  - Project summary presentation materials and validated demo datasets.
- **Measurable Completion Criteria**:
  - Any external engineer can clone the repository, install dependencies, run the test suite, and process a test capture end-to-end to obtain a validated STL.
