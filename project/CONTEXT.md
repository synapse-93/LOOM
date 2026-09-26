# PROJECT CONTEXT — VIDEO2PRINT (LOOM)

**Project**: LOOM / VIDEO2PRINT  
**Objective**: Transition an ordinary smartphone video into a metrically scaled, validated, 3D printable object (.STL) with measurable manufacturing readiness.  
**Last Updated**: 2026-09-26  
**Current Iteration**: 001 (Application Scaffold & Test Hierarchy)  
**Current Milestone**: Phase 0 — Project Bootstrap & Architecture Scaffold (Completed)  

---

## Current Status Snapshot

| Dimension | Status | Notes |
| :--- | :--- | :--- |
| **Codebase State** | Scaffold Operational | Complete modular package `loom` established with 35 passing tests. |
| **Python Target** | 3.10.11 | Installed and active in `.venv` (`.venv\Scripts\python`). |
| **Dependencies** | Minimal Active | `pyyaml`, `pytest` installed in `.venv`. Core CV packages pending Phase 1. |
| **Verified Components** | Core Scaffold (35 Tests) | Config loader, Artifacts, Stage contracts, Runner, Geometry math, CLI. |
| **Active Blockers** | None | Environment active. No blockers for Phase 1. |

---

## Pipeline Component Status

| Pipeline Stage | Module Path | Status | Verified? |
| :--- | :--- | :--- | :--- |
| **0. Project Bootstrap & Scaffold** | `src/loom/`, `tests/` | **COMPLETE** | Yes (35 tests) |
| **1. Video Ingest & Decoding** | `src/loom/video/` | Scaffolded | Interfaces verified |
| **2. Frame Selection & Quality** | `src/loom/capture/` | Scaffolded | Interfaces verified |
| **3. Reconstruction Adapter** | `src/loom/reconstruction/` | Scaffolded | Contract verified |
| **4. Point Cloud Processing** | `src/loom/pointcloud/` | Scaffolded | Interfaces verified |
| **5. Mesh Processing & Cleanup** | `src/loom/mesh/` | Scaffolded | Interfaces verified |
| **6. Metric Scaling** | `src/loom/scaling/` | Scaffolded | Interfaces verified |
| **7. Geometry Validation** | `src/loom/validation/` | Scaffolded | Math verified |
| **8. Printability Analysis** | `src/loom/printability/` | Scaffolded | Reports verified |
| **9. Model Export** | `src/loom/export/` | Scaffolded | Manifests verified |

---

## Key Decisions in Effect

- **ADR-001**: Standardize on Python 3.10.11 runtime.
- **ADR-002**: Initial external reconstruction backend selected as Meshroom / AliceVision CLI.
- **ADR-003**: Reconstruction backend isolated behind `ReconstructionEngine` adapter pattern.
- **ADR-004**: Development metric scaling via known-size physical reference marker (ArUco).

*Details in [`project/DECISIONS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/DECISIONS.md).*

---

## Active & Planned Dependencies

- `pyyaml`: Installed & verified (config loading)
- `pytest`: Installed & verified (test runner)
- `numpy`: Planned (Phase 1)
- `opencv-python`: Planned (Phase 1)
- `open3d`: Planned (Phase 3)
- `trimesh`: Planned (Phase 3)
- `pymeshlab`: Planned (Phase 3)
- `scipy`: Planned (Phase 4)
- `tqdm`: Planned (Phase 1)

---

## Immediate Next Task

**Phase 1 Kickoff (Video Ingest & Frame Quality Module)**:
1. Install `opencv-python` and `numpy` in `.venv`.
2. Implement streaming frame extraction in `src/loom/video/frames.py` and metadata parsing in `src/loom/video/metadata.py`.
3. Implement Laplacian variance sharpness calculation in `src/loom/capture/quality.py`.
4. Create test video fixtures and verify real frame extraction in `tests/unit/video/test_video_ingest.py`.
