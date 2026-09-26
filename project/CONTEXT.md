# PROJECT CONTEXT — VIDEO2PRINT (LOOM)

**Project**: LOOM / VIDEO2PRINT  
**Objective**: Transition an ordinary smartphone video into a metrically scaled, validated, 3D printable object (.STL) with measurable manufacturing readiness.  
**Last Updated**: 2026-09-26  
**Current Iteration**: 002 (Phase 1: Video Ingest, Frame Extraction & Capture Quality)  
**Current Milestone**: Phase 1 — Video Ingest, Frame Extraction & Capture Quality (Completed)  

---

## Current Status Snapshot

| Dimension | Status | Notes |
| :--- | :--- | :--- |
| **Codebase State** | Phase 1 Operational | Real video ingest, streaming extraction, quality analysis, CLI working (52 tests passing). |
| **Python Target** | 3.10.11 | Installed and active in `.venv` (`.venv\Scripts\python`). |
| **Dependencies** | Phase 1 Active | `numpy==2.2.6`, `opencv-python==5.0.0.93`, `pyyaml==6.0.3`, `tqdm==4.70.1`, `pytest==9.1.1`. |
| **Verified Components** | Ingest, Frames, Quality, Pipeline | Streaming frame extraction, blur/exposure/redundancy filter, manifests, reports, CLI. |
| **Active Blockers** | None | Phase 1 verified end-to-end. Ready to plan Phase 2. |

---

## Pipeline Component Status

| Pipeline Stage | Module Path | Status | Verified? |
| :--- | :--- | :--- | :--- |
| **0. Project Bootstrap & Scaffold** | `src/loom/`, `tests/` | **COMPLETE** | Yes (Core architecture) |
| **1. Video Ingest & Decoding** | `src/loom/video/` | **COMPLETE** | Yes (Validation, metadata, streaming) |
| **2. Frame Selection & Quality** | `src/loom/capture/` | **COMPLETE** | Yes (Sharpness, exposure, redundancy, guidance) |
| **3. Reconstruction Adapter** | `src/loom/reconstruction/` | Scaffolded | Contract verified (Phase 2 target) |
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
- **ADR-004**: Metric scaling strategy via known-size physical reference marker (ArUco).
- **ADR-005**: Deterministic frame quality analysis via Laplacian variance, grayscale mean/std exposure, and 64x64 thumbnail mean absolute difference for redundancy.

*Details in [`project/DECISIONS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/DECISIONS.md).*

---

## Active Dependencies

- `numpy==2.2.6`: Active (array math, thumbnail similarity)
- `opencv-python==5.0.0.93`: Active (video decoding, image I/O, Laplacian filtering)
- `pyyaml==6.0.3`: Active (configuration loading)
- `tqdm==4.70.1`: Active (progress feedback)
- `pytest==9.1.1`: Active (testing)

---

## Immediate Next Task

**Phase 2 Planning (Multi-View 3D Reconstruction Integration)**:
1. Design concrete adapter execution for external photogrammetry engine (Meshroom/COLMAP).
2. Establish workspace and output artifact parsing (`camera_poses`, raw `mesh.obj`).
3. Ensure no heavyweight reconstruction binaries pollute core Python package.
