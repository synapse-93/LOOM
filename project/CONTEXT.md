# PROJECT CONTEXT — VIDEO2PRINT (LOOM)

**Project**: LOOM / VIDEO2PRINT  
**Objective**: Transition an ordinary smartphone video into a metrically scaled, validated, 3D printable object (.STL) with measurable manufacturing readiness.  
**Last Updated**: 2026-10-01  
**Current Iteration**: 007 (Phase 4: Metric Scaling Subsystem Implementation & Synthetic Validation)  
**Current Milestone**: Phase 4 — Metric Scaling (IMPLEMENTED & SYNTHETICALLY VERIFIED with 155 total tests; Physical Validation Pending Live Capture with ArUco Fiducial)  

---

## Current Status Snapshot

| Dimension | Status | Notes |
| :--- | :--- | :--- |
| **Codebase State** | Phase 1 Complete, Phase 2 Hardened, Phase 3 Verified, Phase 4 Implemented & Tested | Ingest, quality selection, Meshroom adapter contracts, diagnostics, components, cleanup, conservative repair, normalization, full Phase 1 $\to$ 2 $\to$ 3 handoff, ArUco detection, measurement engine, scale estimator, topology-preserving transformer, scaling processor, and CLI working (155 passing tests). |
| **Python Target** | 3.10.11 | Installed and active in `.venv` (`.venv\Scripts\python`). |
| **Dependencies** | Phase 1, 2, 3 & 4 Active | `numpy==2.2.6`, `opencv-python==5.0.0.93` (`cv2.aruco`), `pyyaml==6.0.3`, `tqdm==4.70.1`, `trimesh==5.1.0`, `scipy==1.15.3`, `pytest==9.1.1`. Zero new third-party dependencies added. Zero heavyweight AI dependencies. |
| **Verified Components** | Ingest, Quality, Reconstruction Adapter, Mesh Diagnostics, Cleanup, Repair, Normalization, Pipeline Handoff, ArUco Detection, Measurement Engine, Scale Estimator, Transformer, Scaling Processor | 155 passing tests verifying photogrammetric mesh processing, component selection, degenerate removal, conservative hole repair, scale calculation, topology-preserving vertex transformation, failure discrimination, and CLI execution (`scale`, `geometry`). |
| **Active Blockers** | Meshroom Host Binary | Neither `meshroom_batch` nor `colmap` is installed on host system (`ISSUE-BLK-002`). Phase 2 live reconstruction remains blocked pending installation. |

---

## Pipeline Component Status

| Pipeline Stage | Module Path | Status | Verified? |
| :--- | :--- | :--- | :--- |
| **0. Project Bootstrap & Scaffold** | `src/loom/`, `tests/` | **COMPLETE** | Yes (Core architecture, 65 tests passing) |
| **1. Video Ingest & Decoding** | `src/loom/video/` | **COMPLETE** | Yes (Validation, metadata, streaming) |
| **2. Frame Selection & Quality** | `src/loom/capture/` | **COMPLETE** | Yes (Sharpness, exposure, redundancy, guidance) |
| **3. Reconstruction Adapter** | `src/loom/reconstruction/` | **IMPLEMENTED** | Yes (Adapter, parsing, failure discrimination verified; host binary missing) |
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
- **ADR-007**: Pure NumPy/SciPy boundary loop extraction, ear-clipping hole triangulation, and BFS winding unification in Phase 3 without external graph engines or AI dependencies.
- **ADR-008**: Strict preservation of reconstructed coordinate values and physical scale during mesh cleanup and normalization (reserving all scaling for Phase 4).
- **ADR-009**: Deterministic metric vertex transformation formulation: $\mathbf{p}_{\text{scaled}} = \mathbf{p}_{\text{orig}} + s \cdot (\mathbf{p} - \mathbf{p}_{\text{orig}})$ with strict topology and face preservation.

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

1. Provision / configure external reconstruction tool (Meshroom / AliceVision or COLMAP) on the host system to unblock live photogrammetry (`ISSUE-BLK-002`).
2. Execute live Phase 2 reconstruction on a real smartphone video of a physical object with an ArUco fiducial marker.
3. Pass live reconstructed mesh through Phase 3 cleanup and Phase 4 metric scaling to physically ground scale recovery.
4. Prepare Phase 5 (Geometry & Ground-Truth Dimensional Validation).



