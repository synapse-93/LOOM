# ISSUES & TECHNICAL DEBT LOG — VIDEO2PRINT

This document tracks active blockers, known limitations, technical debt, research questions, and resolved issues discovered during repository inspection and development.

---

## 1. Active Blockers

- **ISSUE-BLK-002: Meshroom / AliceVision Executable Missing on Development Host**
  - **Discovered**: 2026-09-26 (Phase 2 Environment Discovery)
  - **Description**: `meshroom_batch` is not installed on the development host system. System PATH, standard Windows program directories, and winget registry contain neither AliceVision nor Meshroom.
  - **Impact**: Blocks live 3D reconstruction execution on real capture data until an external backend is installed. `MeshroomAdapter` and `ColmapAdapter` are implemented and covered by mocked subprocess tests; this does not prove a live backend run.
  - **Mitigation**: Use `scripts/reconstruction_smoke_test.py` to check Meshroom availability. Install Meshroom or COLMAP, then use `--reconstruction-backend` with `--reconstruction-binary` (the old `--meshroom-path` option remains an alias).


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

- **ISSUE-LIM-006: Host COLMAP 4.2.1 Windows Build Lacks CUDA Acceleration for Dense MVS**
  - **Discovered**: 2026-10-28 (COLMAP capability audit)
  - **Description**: The precompiled COLMAP 4.2.1 binary at C:\Tools\COLMAP reports 'without GPU support'. While CPU SfM and Delaunay meshing function reliably, dense MVS (patch_match_stereo) requires CUDA/HIP compilation and will fail on CPU.
  - **Impact**: Phase 2 uses CPU Delaunay meshing on sparse SfM tie points. Dense depth maps and dense Poisson meshes cannot be generated until a CUDA-enabled COLMAP build is installed.
  - **Mitigation**: Implemented dynamic capability probing in ColmapAdapter; automatically runs CPU Delaunay meshing path, preserving sparse point clouds and Delaunay meshes without crashing.

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

- **ISSUE-RES-002: Host Photogrammetry Reconstruction Backend Operational**
  - **Resolved**: 2026-10-28 (Iteration 009)
  - **Description**: Development host previously lacked an operational photogrammetry backend, blocking live 3D reconstruction on real footage (ISSUE-BLK-002).
  - **Resolution**: COLMAP 4.2.1 configured and hardened at C:\Tools\COLMAP. Resolved Windows Qt platform plugin path requirement (QT_QPA_PLATFORM_PLUGIN_PATH), implemented CPU feature extraction/matching flags, SQLite match validation, and CGAL Delaunay meshing. Verified live end-to-end execution on smartphone video (EXP-009).

- **ISSUE-RES-003: Pipeline Integration Defect Remediation & Configuration Persistence**
  - **Resolved**: 2026-10-28 (Iteration 012)
  - **Description**: Cross-stage pipeline review uncovered 6 integration defects: (1) dropped `capture.min_texture_score` in loader and unsafe attribute access in quality assessor, (2) dropped 10 `MeshConfig` parameters in loader leading to lost user settings, (3) case-sensitive `--log-level` CLI failure and dropped `voxel_downsample_size: 0.0`, (4) global COLMAP argument rejections and missing intermediate workspace cleanup, (5) unhandled `ValueError` in printability wall-thickness analysis when evaluating non-watertight meshes, and (6) missing end-to-end multi-stage integration coverage.
  - **Resolution**: Implemented test-first fixes for all 6 issues: restored all `CaptureConfig` and `MeshConfig` field persistence, made `--log-level` case-insensitive, implemented namespaced argument routing for COLMAP subcommands (`_extract_subcommand_args`), added graceful non-watertight handling in `PrintabilityReportGenerator.generate_report`, and added end-to-end tests validating the full handoff from YAML to STL. 206 passing tests.
- **ISSUE-RES-004: Frame Extraction Premature Truncation Under max_frames Limit**
  - **Resolved**: 2026-10-29 (Iteration 013)
  - **Description**: FrameExtractor evaluated frame step based solely on source FPS and target_fps, then stopped extraction as soon as max_frames was reached. On long captures (e.g. 63s video, 3,778 frames @ 60fps), requesting 60 frames halted extraction at frame 236 (t = 3.95s), skipping 93.75% of the video and causing all sharp frames later in the orbit to be missed. In addition, direct imports of loom.video modules triggered a circular import cycle through loom.pipeline.
  - **Resolution**: Updated FrameExtractor in src/loom/video/frames.py to dynamically inflate the sampling step to max(step, source_frame_count // max_frames) when nominal frames exceed max_frames. This guarantees uniform coverage across the full video duration while strictly respecting max_frames. Decoupled loom.video from loom.pipeline at import time by moving FrameSetArtifact and VideoArtifact behind TYPE_CHECKING and importing locally inside methods. Verified 210 passing tests and 96.82% empirical coverage on full smartphone video.
- **ISSUE-RES-005: Match-Graph Disconnection from Clustered Single-Threshold Frame Filtering**
  - **Resolved**: 2026-10-29 (Iteration 014)
  - **Description**: Hard per-frame sharpness filtering (`sharpness < 80.0`) discarded 43 of 60 frames extracted from `video_20261029_152036.mp4`, clustering 14 frames between $t=16$s–$32$s followed by a 24-second tracking void. The resulting candidate match graph was partitioned into 4 disconnected components and homography-dominated pairs ($H/F > 0.95$), causing COLMAP mapper initialization to discard all candidate pairs and fail.
  - **Resolution**: Implemented opt-in `ReconstructionAwareSelector` in `src/loom/capture/reconstruction_aware.py`. Features uniform temporal bucketing across video duration, multi-factor optical quality scoring, pairwise Fundamental matrix vs Homography RANSAC verification in a bounded sliding window ($K=3$), planar/rotational motion discrimination ($H/F \ge 0.85$), and bridge frame prioritization to reconnect disjoint subgraphs. Preserved 100% backward compatibility for `selection_mode = "default"`.

- **ISSUE-RES-006: OpenCV VideoCapture C++ Subclassing in Test Fixture Causing Windows GC Access Violation**
  - **Resolved**: 2026-10-29 (Iteration 014)
  - **Description**: In `tests/unit/video/test_frames.py`, `test_frame_extraction_handles_unknown_frame_count` subclassed `cv2.VideoCapture` in Python. Because OpenCV's C extension types lack a Python-compatible heap layout for subclassing, Python's garbage collector crashed on teardown with a fatal access violation in `gc_collect_harder`.
  - **Resolution**: Refactored the test mock to use composition with `VideoCaptureWrapper` delegating method calls to `self._real`, cleanly avoiding C++ inheritance in Python and resolving the GC access violation.

- **ISSUE-RES-007: Single-Model Binding Defect in Multi-Component COLMAP SfM & Delaunay Meshing Spike Suppression**
  - **Resolved**: 2026-10-29 (Iteration 015)
  - **Description**: `ColmapAdapter.reconstruct()` unconditionally bound to `sparse_dir / "0"`. When mapping partitioned the scene into multiple models, `sparse/0` was often a small discarded 5-camera fragment (209 points), while `sparse/1` contained the primary reconstruction with 21–24 registered cameras and 874–983 points. In addition, Delaunay meshing on sparse points used default factor 25, creating giant 24.7-meter outlier edges stretching the bounding box extent to 28.8m.
  - **Resolution**: Implemented `_get_model_stats()` in `src/loom/reconstruction/colmap.py` to inspect binary/text models and dynamically select the optimal model maximizing registered cameras and point counts. Enforced `--DelaunayMeshing.max_side_length_factor 10` by default, suppressing edge spikes and bounding the reconstructed surface tightly (8.63m x 11.14m x 3.68m). Added adequacy validation raising `ReconstructionExecutionError` when registered cameras < 3 and marking `ReconstructionStatus.PARTIAL` when coverage < 35%. 223 passing tests.
