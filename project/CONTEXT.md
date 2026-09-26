# PROJECT CONTEXT — VIDEO2PRINT (LOOM)

**Project**: LOOM / VIDEO2PRINT  
**Objective**: Transition an ordinary smartphone video into a metrically scaled, validated, 3D printable object (.STL) with measurable manufacturing readiness.  
**Last Updated**: 2026-09-26  
**Current Iteration**: 003 (Phase 1.5: Verification & Hardening, Phase 2: Meshroom 3D Reconstruction Adapter)  
**Current Milestone**: Phase 2 — Multi-View 3D Reconstruction Integration (Adapter IMPLEMENTED & VERIFIED with mocked subprocess; Live execution BLOCKED pending host binary installation)  

---

## Current Status Snapshot

| Dimension | Status | Notes |
| :--- | :--- | :--- |
| **Codebase State** | Phase 1 Verified, Phase 2 Implemented | Real video ingest, streaming extraction, quality filtering, Meshroom adapter implemented, CLI `--reconstruct` working (65 tests passing). |
| **Python Target** | 3.10.11 | Installed and active in `.venv` (`.venv\Scripts\python`). |
| **Dependencies** | Phase 1 & 2 Active | `numpy==2.2.6`, `opencv-python==5.0.0.93`, `pyyaml==6.0.3`, `tqdm==4.70.1`, `pytest==9.1.1`. Zero heavyweight AI dependencies. |
| **Verified Components** | Ingest, Frames, Quality, Pipeline, Reconstruction Adapter | Frame extraction, blur/exposure/redundancy filter, reports, Meshroom adapter (mocked subprocess), CLI. |
| **Active Blockers** | Meshroom Host Binary | Neither `meshroom_batch` nor `colmap` is installed on host system. Live reconstruction blocked until installed or path configured (`ISSUE-BLK-002`). |

---

## Pipeline Component Status

| Pipeline Stage | Module Path | Status | Verified? |
| :--- | :--- | :--- | :--- |
| **0. Project Bootstrap & Scaffold** | `src/loom/`, `tests/` | **COMPLETE** | Yes (Core architecture, 65 tests passing) |
| **1. Video Ingest & Decoding** | `src/loom/video/` | **COMPLETE** | Yes (Validation, metadata, streaming) |
| **2. Frame Selection & Quality** | `src/loom/capture/` | **COMPLETE** | Yes (Sharpness, exposure, redundancy, guidance) |
| **3. Reconstruction Adapter** | `src/loom/reconstruction/` | **IMPLEMENTED** | Yes (Adapter verified with mocked subprocess; host binary missing) |
| **4. Point Cloud Processing** | `src/loom/pointcloud/` | Scaffolded | Interfaces verified |
| **5. Mesh Processing & Cleanup** | `src/loom/mesh/` | Scaffolded | Interfaces verified (Phase 3 target) |
| **6. Metric Scaling** | `src/loom/scaling/` | Scaffolded | Interfaces verified (Phase 4 target) |
| **7. Geometry Validation** | `src/loom/validation/` | Scaffolded | Math verified (Phase 5 target) |
| **8. Printability Analysis** | `src/loom/printability/` | Scaffolded | Reports verified (Phase 6 target) |
| **9. Model Export** | `src/loom/export/` | Scaffolded | Manifests verified (Phase 7 target) |

---

## Key Decisions in Effect

- **ADR-001**: Standardize on Python 3.10.11 runtime.
- **ADR-002**: Initial external reconstruction backend selected as Meshroom / AliceVision CLI.
- **ADR-003**: Reconstruction backend isolated behind `ReconstructionEngine` adapter pattern.
- **ADR-004**: Metric scaling strategy via known-size physical reference marker (ArUco).
- **ADR-005**: Deterministic frame quality analysis via Laplacian variance, grayscale mean/std exposure, and 64x64 thumbnail mean absolute difference for redundancy.
- **ADR-006**: Subprocess execution isolation, safe timeout handling, `cameras.sfm` registration parsing, and controlled output artifact discovery for Meshroom.

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

1. Provide / install Meshroom 2023.3 binary on host or configure `--meshroom-path`.
2. Provide a real smartphone capture following [`docs/capture/capture_guide.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/docs/capture/capture_guide.md) to execute the first live end-to-end 3D reconstruction.
3. Inspect the resulting raw mesh (`texturedMesh.obj`) before initiating Phase 3 (Mesh Cleanup & Processing).
