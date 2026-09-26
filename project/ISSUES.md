# ISSUES & TECHNICAL DEBT LOG — VIDEO2PRINT

This document tracks active blockers, known limitations, technical debt, research questions, and resolved issues discovered during repository inspection and development.

---

## 1. Active Blockers

- **ISSUE-BLK-001: Python 3.10.11 Binary Missing from Registered Path on Host**
  - **Discovered**: 2026-09-26 (Repository inspection)
  - **Description**: The Windows `py` launcher registry lists `Python 3.10.11` mapped to `C:\Users\adise\AppData\Local\Python\pythoncore-3.10-64\python.exe`, but this executable path does not exist on disk. The active system interpreter in PATH is Python 3.14.7 (`C:\Python314\python.exe`).
  - **Impact**: Running `py -3.10 -m venv .venv` fails with "The system cannot find the file specified". Furthermore, Python 3.14 cannot be used as an alternative because pre-compiled binary wheels for `pymeshlab` and `open3d` do not exist for Python 3.14.
  - **Required Action**: Install Python 3.10.11 64-bit on the host machine (e.g. via `winget install Python.Python.3.10` or official Python installer) before initializing `.venv` for Phase 1.

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
