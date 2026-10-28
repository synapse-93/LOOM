# PROJECT CONTEXT — VIDEO2PRINT (LOOM)

**Project**: LOOM / VIDEO2PRINT  
**Objective**: Transition an ordinary smartphone video into a metrically scaled, validated, 3D printable object (.STL) with measurable manufacturing readiness.  
**Last Updated**: 2026-10-28  
**Current Iteration**: 009 (COLMAP Windows CPU Reconstruction Pipeline, Qt Plugin Resolution & Live End-to-End Verification)  
**Current Milestone**: Phase 2 — Photogrammetry Reconstruction (VERIFIED on Windows Host via COLMAP 4.2.1); Phase 3 (VERIFIED); Phase 4 (IMPLEMENTED & SYNTHETICALLY VERIFIED with 171 total tests)  

---

## Current Status Snapshot

| Dimension | Status | Notes |
| :--- | :--- | :--- |
| **Codebase State** | Phase 1 Complete, Phase 2 Verified (COLMAP), Phase 3 Verified, Phase 4 Implemented | Ingest, quality selection, COLMAP & Meshroom adapters, diagnostics, components, cleanup, repair, normalization, Phase 1 $\to$ 2 $\to$ 3 handoff, ArUco detection, measurement engine, scale estimator, transformer, scaling processor, and CLI working (171 passing tests). |
| **Python Target** | 3.10.11 | Installed and active in `.venv` (`.venv\Scripts\python`). |
| **Dependencies** | Phase 1, 2, 3 & 4 Active | `numpy==2.2.6`, `opencv-python==5.0.0.93` (`cv2.aruco`), `pyyaml==6.0.3`, `tqdm==4.70.1`, `trimesh==5.1.0`, `scipy==1.15.3`, `pytest==9.1.1`. Zero new third-party dependencies. Zero heavyweight AI dependencies. |
| **Verified Components** | Ingest, Quality, COLMAP Adapter (CPU/Qt/Delaunay), Mesh Diagnostics, Cleanup, Repair, Normalization, Pipeline Handoff, ArUco Detection, Measurement Engine, Scale Estimator, Transformer, Scaling Processor, Zero-Frame Guard | 171 passing tests verifying photogrammetric mesh processing, component selection, degenerate removal, conservative hole repair, scale calculation, topology-preserving vertex transformation, failure discrimination, and CLI execution (`scale`, `geometry`, `reconstruct`). |
| **Active Blockers** | None | COLMAP 4.2.1 is installed at `C:\Tools\COLMAP` and verified functional for live photogrammetry on host Windows environment (`EXP-008`). |

---

## Pipeline Component Status

| Pipeline Stage | Module Path | Status | Verified? |
| :--- | :--- | :--- | :--- |
| **0. Project Bootstrap & Scaffold** | `src/loom/`, `tests/` | **COMPLETE** | Yes (Core architecture, 65 tests passing) |
| **1. Video Ingest & Decoding** | `src/loom/video/` | **COMPLETE** | Yes (Validation, metadata, streaming) |
| **2. Frame Selection & Quality** | `src/loom/capture/` | **COMPLETE** | Yes (Sharpness, exposure, redundancy, guidance) |
| **3. Reconstruction Adapter** | `src/loom/reconstruction/` | **VERIFIED** | Yes (COLMAP 4.2.1 verified live on host; Meshroom adapter contract verified) |
| **4. Point Cloud Processing** | `src/loom/pointcloud/` | Scaffolded | Interfaces verified |
| **5. Mesh Processing & Cleanup** | `src/loom/mesh/` | **VERIFIED** | Yes (Diagnostics, components, cleanup, conservative repair, normal unification, 49 tests passing) |
| **6. Metric Scaling** | `src/loom/scaling/` | **IMPLEMENTED / SYNTHETICALLY VERIFIED** | Yes (ArUco detection, measurement engine, scale estimator, transformer, processor, CLI, 31 tests passing) |
| **7. Geometry Validation** | `src/loom/validation/` | Scaffolded | Math verified (Phase 5 target) |
| **8. Printability Analysis** | `src/loom/printability/` | Scaffolded | Reports verified (Phase 6 target) |
| **9. Model Export** | `src/loom/export/` | Scaffolded | Manifests verified (Phase 7 target) |

---

## Key Decisions in Effect

- **ADR-001**: Standardize on Python 3.10.11 runtime.
- **ADR-002**: Initial external reconstruction backend selected as Meshroom / AliceVision CLI.
- **ADR-003**: Reconstruction backend isolated behind `ReconstructionEngine` adapter pattern.
- **ADR-004**: Metric scaling strategy via known-size physical reference marker (ArUco).
- **ADR-005**: Deterministic frame quality analysis via Laplacian variance, grayscale exposure, and 64x64 thumbnail difference.
- **ADR-006**: Subprocess execution isolation, safe timeout handling, `cameras.sfm` registration parsing for Meshroom.
- **ADR-007**: Pure NumPy/SciPy boundary loop extraction, ear-clipping hole triangulation, and BFS winding unification in Phase 3.
- **ADR-008**: Strict preservation of reconstructed coordinate values and physical scale during mesh cleanup and normalization.
- **ADR-009**: Deterministic metric vertex transformation formulation with topology preservation.
- **ADR-010**: CPU-compatible COLMAP reconstruction pipeline, relative Qt platform plugin discovery, and SQLite match verification.

*Details in [`project/DECISIONS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/DECISIONS.md).*

---

## Active Dependencies

- `numpy==2.2.6`: Active (array math, vector operations, coordinate manipulation)
- `opencv-python==5.0.0.93`: Active (video decoding, image I/O, Laplacian filtering, `cv2.aruco`)
- `trimesh==5.1.0`: Active (mesh I/O, topology inspection, bounding box, export, transformation)
- `scipy==1.15.3`: Active (spatial adjacency, graph components)
- `pyyaml==6.0.3`: Active (configuration loading)
- `tqdm==4.70.1`: Active (progress feedback)
- `pytest==9.1.1`: Active (testing)

---

## Immediate Next Task

1. Capture a physical object with a known-size physical ArUco fiducial marker to run Phase 1 $\to$ Phase 2 (COLMAP) $\to$ Phase 3 (Mesh Cleanup) $\to$ Phase 4 (Metric Scaling) end-to-end to validate physical metric scaling.
2. Implement Phase 5 (Geometry & Ground-Truth Dimensional Validation).
