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
- **Status**: NOT STARTED
- **Objective**: Integrate external photogrammetry engine via an abstract adapter interface.
- **Prerequisites**: Phase 1 complete; Meshroom / AliceVision binaries configured or mocked for CI.
- **Expected Deliverables**:
  - `src/video2print/reconstruction/base.py`: `ReconstructionEngine` abstract base class and dataclasses.
  - `src/video2print/reconstruction/meshroom.py`: Subprocess adapter for AliceVision / Meshroom CLI.
  - Mock reconstruction adapter for deterministic headless unit tests.
- **Measurable Completion Criteria**:
  - Adapter successfully builds execution command, manages scratch directories, runs subprocess, and returns `ReconstructionResult`.
  - Generates valid `.obj` or `.ply` mesh from valid input frames.
  - Gracefully catches timeouts or missing binaries with descriptive `ReconstructionError`.

---

### Phase 3: Raw Geometry Processing & Mesh Cleanup
- **Status**: NOT STARTED
- **Objective**: Clean and repair raw photogrammetric output meshes.
- **Prerequisites**: Phase 2 complete (or sample raw photogrammetry mesh fixtures available).
- **Expected Deliverables**:
  - `src/video2print/mesh/`: Outlier cluster removal, duplicate vertex welding, normal unification, surface hole filling, and Screened Poisson surface reconstruction.
  - Unit tests in `tests/unit/test_mesh_processing.py` on synthetic dirty meshes.
- **Measurable Completion Criteria**:
  - Raw mesh with disconnected floating fragments is cleaned to a single primary component.
  - Unreferenced vertices and self-intersecting faces are eliminated or flagged.

---

### Phase 4: Metric Scaling Subsystem
- **Status**: NOT STARTED
- **Objective**: Overcome monocular scale ambiguity by detecting physical fiducial markers and scaling the mesh to real-world millimeters.
- **Prerequisites**: Phase 3 complete; `opencv-python` (ArUco module) and sample frames with known markers.
- **Expected Deliverables**:
  - `src/video2print/scaling/`: Fiducial detector (ArUco / reference board), 3D plane/point distance estimator, scale factor calculator ($s = d_{\text{physical}} / d_{\text{reconstructed}}$), and transformation matrix applicator.
  - Unit tests in `tests/unit/test_metric_scaling.py`.
- **Measurable Completion Criteria**:
  - Given an unscaled mesh with a known 50.0 mm ArUco marker, correctly scales the mesh geometry so that the reference marker measures $50.0 \pm 1.0\text{ mm}$ in mesh coordinate space.

---

### Phase 5: Geometry Validation
- **Status**: NOT STARTED
- **Objective**: Quantitatively compare reconstructed mesh geometry against known physical ground-truth dimensions and reference CAD geometry.
- **Prerequisites**: Phase 4 complete; reference geometric test object (e.g. 50mm gauge cube).
- **Expected Deliverables**:
  - `src/video2print/validation/`: Bounding box calculator, cross-sectional caliper measurement simulator, Hausdorff distance calculator (mesh-to-mesh / point-to-mesh).
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
  - `src/video2print/printability/`: Watertightness checker (is_watertight), non-manifold edge detector, minimum wall thickness checker, overhang angle analyzer ($> 45^\circ$).
  - `src/video2print/export/`: Binary STL exporter with optimal build orientation recommendation.
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
  - Clean CLI entrypoint (`video2print run input.mp4 --output-dir ./output`).
  - Project summary presentation materials and validated demo datasets.
- **Measurable Completion Criteria**:
  - Any external engineer can clone the repository, install dependencies, run the test suite, and process a test capture end-to-end to obtain a validated STL.
