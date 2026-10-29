# PROJECT CONTEXT — VIDEO2PRINT (LOOM)

**Project**: LOOM / VIDEO2PRINT
**Objective**: Transition an ordinary smartphone video into a metrically scaled, validated, 3D printable object (.STL) with measurable manufacturing readiness.
**Last Updated**: 2026-10-29
**Current Iteration**: 015 (Multi-Model SfM Selection & Dense Sampling Evaluation) (Reconstruction-Aware Frame Selection & Geometric Verification)
**Current Milestone**: Phase 1 Frame Selection (VERIFIED with default and reconstruction-aware modes); Phase 2 Photogrammetry (VERIFIED on Windows Host via COLMAP 4.2.1); Phase 3 (VERIFIED); Phase 4 (IMPLEMENTED & SYNTHETICALLY VERIFIED); Phase 6 Printability (VERIFIED); Phase 7 STL Export (VERIFIED) with 223 total tests

---

## Current Status Snapshot

| Dimension | Status | Notes |
| :--- | :--- | :--- |
| **Codebase State** | Full Pipeline Stages 1, 2 (COLMAP/Meshroom), 3, 4, 6 (Printability), 7 (STL Export) Integrated, Debugged & Verified | Ingest, default & reconstruction-aware frame selection, COLMAP & Meshroom adapters, diagnostics, components, cleanup, repair, normalization, Phase 1 $\to$ 2 $\to$ 3 handoff, ArUco detection, measurement engine, scale estimator, transformer, scaling processor, printability report generator, STL exporter, and CLI working (223 passing tests). |
| **Python Target** | 3.10.11 | Installed and active in `.venv` (`.venv\Scripts\python`). |
| **Dependencies** | Minimal active dependencies | `numpy==2.2.6`, `opencv-python==5.0.0.93` (`cv2.aruco`), `pyyaml==6.0.3`, `tqdm==4.70.1`, `trimesh==5.1.0`, `scipy==1.15.3`, `pytest==9.2.0`, `rtree==1.4.1`. Zero heavyweight AI dependencies. |
| **Verified Components** | Ingest, Full-Duration Frame Extraction, Quality Selection (Default & Reconstruction-Aware), COLMAP Adapter (CPU/Qt/Delaunay), Mesh Diagnostics, Cleanup, Repair, Normalization, Pipeline Handoff, ArUco Detection, Measurement Engine, Scale Estimator, Transformer, Scaling Processor, Printability Orchestrator, STL Exporter, CLI Options | 220 passing tests verifying reconstruction-aware temporal bucketing, Fundamental vs Homography parallax check, bridge frame prioritization, photogrammetric mesh processing, component selection, degenerate removal, conservative hole repair, scale calculation, topology-preserving vertex transformation, failure discrimination, non-watertight printability handling, full video duration extraction, and CLI execution. |
| **Active Blockers** | None | COLMAP 4.2.1 is installed and verified functional for live photogrammetry on host Windows environment (`EXP-008`). |

---

## Pipeline Component Status

| Pipeline Stage | Module Path | Status | Verified? |
| :--- | :--- | :--- | :--- |
| **0. Project Bootstrap & Scaffold** | `src/loom/`, `tests/` | **COMPLETE** | Yes (Core architecture, 65 tests passing) |
| **1. Video Ingest & Decoding** | `src/loom/video/` | **COMPLETE** | Yes (Validation, metadata, streaming, full-duration sampling) |
| **2. Frame Selection & Quality** | `src/loom/capture/` | **COMPLETE** | Yes (Default optical thresholds & opt-in reconstruction-aware mode, 24 tests passing) |
| **3. Reconstruction Adapter** | `src/loom/reconstruction/` | **VERIFIED** | Yes (COLMAP 4.2.1 verified live on host; Meshroom adapter contract verified) |
| **4. Point Cloud Processing** | `src/loom/pointcloud/` | Scaffolded | Interfaces verified |
| **5. Mesh Processing & Cleanup** | `src/loom/mesh/` | **VERIFIED** | Yes (Diagnostics, components, cleanup, conservative repair, normal unification, 49 tests passing) |
| **6. Metric Scaling** | `src/loom/scaling/` | **IMPLEMENTED / SYNTHETICALLY VERIFIED** | Yes (ArUco detection, measurement engine, scale estimator, transformer, processor, CLI, 31 tests passing) |
| **7. Geometry Validation** | `src/loom/validation/` | Scaffolded | Math verified (Phase 5 target) |
| **8. Printability Analysis** | `src/loom/printability/` | **VERIFIED** | Yes (Watertight, manifold, overhang, wall thickness, graceful report orchestration) |
| **9. Model Export** | `src/loom/export/` | **VERIFIED** | Yes (Binary and ASCII STL export, bounds invariant) |

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
- **ADR-011**: Reconstruction-aware keyframe selection with temporal bucketing, local sliding window ($K=3$) $F$ vs $H$ geometric verification, and bridge frame prioritization.

---

## Active Dependencies

- `numpy==2.2.6`: Active (array math, vector operations, coordinate manipulation)
- `opencv-python==5.0.0.93`: Active (video decoding, image I/O, Laplacian filtering, `cv2.aruco`, feature matching, $F$ and $H$ estimation)
- `pyyaml==6.0.3`: Active (configuration file management)
- `tqdm==4.70.1`: Active (progress visualization)
- `trimesh==5.1.0`: Active (mesh I/O, raycasting for wall thickness, watertight validation)
- `scipy==1.15.3`: Active (spatial KDTree nearest neighbors, graph traversal)
- `rtree==1.4.1`: Active (spatial indexing for fast ray queries)
