# PROJECT CONTEXT — VIDEO2PRINT

**Project**: VIDEO2PRINT  
**Objective**: Transition an ordinary smartphone video into a metrically scaled, validated, 3D printable object (.STL) with measurable manufacturing readiness.  
**Last Updated**: 2026-09-26  
**Current Iteration**: 000 (Project Bootstrap)  
**Current Milestone**: Phase 0 — Project Bootstrap (Completed)  

---

## Current Status Snapshot

| Dimension | Status | Notes |
| :--- | :--- | :--- |
| **Codebase State** | Empty / Initialized | Project governance and rules established. No application code written yet. |
| **Python Target** | 3.10.11 | Registered in `py` launcher, but binary missing on disk. Must install Python 3.10 before venv setup. |
| **Dependencies** | Proposed / Uninstalled | Core dependencies defined in rules; not yet installed in `.venv`. |
| **Verified Components** | None | Pipeline implementation has not started. |
| **Active Blockers** | ISSUE-BLK-001 | Python 3.10.11 binary missing from disk; must install to create `.venv`. |

---

## Pipeline Component Status

| Pipeline Stage | Module Path | Status | Verified? |
| :--- | :--- | :--- | :--- |
| **0. Project Bootstrap** | `.agents/`, `project/` | **COMPLETE** | Yes |
| **1. Video Ingest & Decoding** | `src/video2print/video/` | NOT STARTED | No |
| **2. Frame Selection & Quality** | `src/video2print/frames/` | NOT STARTED | No |
| **3. Reconstruction Adapter** | `src/video2print/reconstruction/` | NOT STARTED | No |
| **4. Mesh Processing & Cleanup** | `src/video2print/mesh/` | NOT STARTED | No |
| **5. Metric Scaling** | `src/video2print/scaling/` | NOT STARTED | No |
| **6. Geometry Validation** | `src/video2print/validation/` | NOT STARTED | No |
| **7. Printability Analysis** | `src/video2print/printability/` | NOT STARTED | No |
| **8. Model Export** | `src/video2print/export/` | NOT STARTED | No |

---

## Key Decisions in Effect

- **ADR-001**: Standardize on Python 3.10.11 runtime.
- **ADR-002**: Initial external reconstruction backend selected as Meshroom / AliceVision CLI.
- **ADR-003**: Reconstruction backend isolated behind `ReconstructionEngine` adapter pattern.
- **ADR-004**: Development metric scaling via known-size physical reference marker (ArUco).

*Details in [`project/DECISIONS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/DECISIONS.md).*

---

## Planned Core Dependencies

- `numpy`
- `opencv-python`
- `open3d`
- `trimesh`
- `pymeshlab`
- `scipy`
- `tqdm`
- `pyyaml`
- `pytest` (test runner)

---

## Immediate Next Task

**Phase 1 Kickoff**:
1. Resolve ISSUE-BLK-001 by installing Python 3.10.11 64-bit on host (e.g. via `winget install Python.Python.3.10`), then initialize virtual environment using `py -3.10 -m venv .venv`.
2. Create `requirements.txt` with initial core dependencies and install into `.venv`.
3. Create `src/video2print/video/` and implement video ingest, frame extraction, and metadata extraction.
4. Create `tests/unit/test_video_ingest.py` with synthetic/sample fixtures and verify tests pass.
