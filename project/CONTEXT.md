# PROJECT CONTEXT — VIDEO2PRINT (LOOM)

**Project**: LOOM / VIDEO2PRINT  
**Objective**: Transition an ordinary smartphone video into a metrically scaled, validated, 3D printable object (.STL) with measurable manufacturing readiness.  
**Last Updated**: 2026-10-01  
**Current Iteration**: 006 (Phase 2 & Phase 3 Validation, Hardening & Pipeline Handoff Audit)  
**Current Milestone**: Phase 2 — Reconstruction Backend Integration (Adapter & Contracts Verified; Host Binary BLOCKED `ISSUE-BLK-002`); Phase 3 — Raw Geometry & Mesh Processing (VERIFIED & AUDITED with 124 total tests)  

---

## Current Status Snapshot

| Dimension | Status | Notes |
| :--- | :--- | :--- |
| **Codebase State** | Phase 1 Complete, Phase 2 Hardened, Phase 3 Verified & Audited | Video ingest, quality selection, Meshroom adapter contracts, diagnostics, components, cleanup, conservative repair, normalization, and full Phase 1 $\to$ 2 $\to$ 3 handoff working (124 passing tests). |
| **Python Target** | 3.10.11 | Installed and active in `.venv` (`.venv\Scripts\python`). |
| **Dependencies** | Phase 1, 2 & 3 Active | `numpy==2.2.6`, `opencv-python==5.0.0.93`, `pyyaml==6.0.3`, `tqdm==4.70.1`, `trimesh==5.1.0`, `scipy==1.15.3`, `pytest==9.1.1`. Zero heavyweight AI dependencies. |
| **Verified Components** | Ingest, Quality, Reconstruction Adapter, Mesh Diagnostics, Cleanup, Repair, Normalization, Pipeline Handoff | 124 passing tests verifying photogrammetric mesh processing, component selection, degenerate removal, conservative hole repair, scale/coordinate preservation, failure discrimination, and CLI execution. |
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
- **ADR-005**: Deterministic frame quality analysis via Laplacian variance, grayscale exposure, and 64x64 thumbnail difference.
- **ADR-006**: Subprocess execution isolation, safe timeout handling, `cameras.sfm` registration parsing for Meshroom.
- **ADR-007**: Pure NumPy/SciPy boundary loop extraction, ear-clipping hole triangulation, and BFS winding unification in Phase 3 without external graph engines or AI dependencies.
- **ADR-008**: Strict preservation of reconstructed coordinate values and physical scale during mesh cleanup and normalization (reserving all scaling for Phase 4).

*Details in [`project/DECISIONS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/DECISIONS.md).*

---

## Active Dependencies

- `numpy==2.2.6`: Active (array math, vector operations, coordinate manipulation)
- `opencv-python==5.0.0.93`: Active (video decoding, image I/O, Laplacian filtering)
- `trimesh==5.1.0`: Active (mesh I/O, topology inspection, bounding box, export)
- `scipy==1.15.3`: Active (spatial adjacency, graph components)
- `pyyaml==6.0.3`: Active (configuration loading)
- `tqdm==4.70.1`: Active (progress feedback)
- `pytest==9.1.1`: Active (testing)

---

## Immediate Next Task

1. Provision / configure external reconstruction tool (Meshroom / AliceVision or COLMAP) on the host system to unblock live photogrammetry (`ISSUE-BLK-002`).
2. Execute live Phase 2 reconstruction on a real smartphone video of a physical object with an ArUco fiducial marker.
3. Feed the resulting live raw `texturedMesh.obj` into Phase 3 (`python -m loom geometry --input <raw_mesh>`) to validate the complete Phase 1 -> Phase 2 -> Phase 3 pipeline on live capture.
4. Prepare Phase 4 (Fiducial Metric Scaling & Coordinate Transformation).


