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
