# PROJECT CONTEXT — VIDEO2PRINT (LOOM)

**Project**: LOOM / VIDEO2PRINT  
**Objective**: Transition an ordinary smartphone video into a metrically scaled, validated, 3D printable object (.STL) with measurable manufacturing readiness.  
**Last Updated**: 2026-11-21  
**Current Iteration**: 025 (Phase 1 Core Stabilization, Geometric Defect Resolution, and Repo Hygiene)  
**Current Milestone**: Phase 1 Stabilization Complete — 248/248 Tests Passing, Zero Blocking Defects  

---

## Current Status Snapshot

| Dimension | Status | Notes |
| :--- | :--- | :--- |
| **Codebase State** | Stabilized & 100% Green | Fixed `IndentationError` in `src/loom/mesh/processor.py`, hardened `CoordinateNormalizer` (full-cloud RANSAC + camera-centroid polarity + synchronous unit-normal Rodrigues $SO(3)$ rotation), verified `--PoissonMeshing.trim 0` & $<75\%$ SfM circuit breaker in `colmap.py`, added automatic `/opt/cuda/lib64` `LD_LIBRARY_PATH` prepending in `src/loom/utils/subprocess.py`, generalized `scripts/demo.py` `--target-length` default to `200.0` mm in `float64` with $Z_{\min}=0.000000$ snap, purged stray root Vite/React files, and synced `AGENTS.md`, `ARCHITECTURE.md`, `README.md`. |
| **Runtime Environment** | Linux / Active `.venv` | Host `.venv` runs Python 3.14.9 (code remains Python 3.10+ compatible via `from __future__ import annotations`). `open3d` remains strictly optional. |
| **Dependencies & Hardware** | Core Active | `numpy==2.5.4`, `scipy==1.18.1`, `trimesh==5.2.0`, `opencv-python==5.0.0.93`, `mapbox-earcut==2.1.0`, `pyyaml==6.0.3`, `pytest==9.2.0`. Native `COLMAP 4.2.0 (Commit be5e29168 on 2026-08-31 with CUDA)` at `/usr/bin/colmap`, NVIDIA GeForce RTX 4060 Laptop GPU (8188 MiB VRAM, Driver 615.78.08). |
| **Verification Status** | **248 passed in 4.84s** | `.venv/bin/pytest tests/ -q` passes 100% (0 failed, 0 errors). `run_subprocess(['colmap', '-h'])` exits `0` with CUDA linker path auto-injected. |
| **Active Blockers** | None | All Phase 1 stabilization blockers resolved. |

---

## Pipeline Component Status

| Pipeline Stage | Module Path | Status | Verified? |
| :--- | :--- | :--- | :--- |
| **1. Video Ingest & Filtering** | `src/loom/video/` | **COMPLETE** | Yes (960px `INTER_AREA`, 68 turbo frames, Laplacian $\tau=18.0$) |
| **2. Capture Quality** | `src/loom/capture/` | **COMPLETE** | Yes (Sharpness, exposure, redundancy, coverage) |
| **3. Reconstruction Adapter** | `src/loom/reconstruction/` | **COMPLETE** | Yes (COLMAP 4.2.0 CUDA, sequential overlap 10, $<75\%$ SfM circuit breaker, Poisson depth 10 / `trim=0`) |
| **4. Canonical Alignment & Segmentation** | `src/loom/geometry/` | **COMPLETE** | Yes (Full-cloud RANSAC 1500 iters, camera-centroid polarity, Rodrigues $SO(3)$ vertices + unit normals, cylindrical crop) |
| **5. Mesh Processing & Repair** | `src/loom/mesh/` | **COMPLETE** | Yes (`processor.py` syntax fixed, KDTree culling, `mapbox-earcut` base cap, $>60$ edge anti-starburst guard) |
| **6. Metric Scaling** | `src/loom/scaling/` | **COMPLETE** | Yes (ArUco DLT scaling + float64 `--target-length` default 200.0 mm + $Z_{\min}=0.0$ snap) |
| **7. Validation & Printability Gate** | `src/loom/validation/`, `src/loom/printability/` | **COMPLETE** | Yes (AABB/OBB dims, watertight, 2-manifold, positive volume gate) |
| **8. Binary STL Export & Subprocess** | `src/loom/export/`, `src/loom/utils/` | **COMPLETE** | Yes (Validated binary STL + manifest, `/opt/cuda/lib64` auto-prepended in `run_subprocess`) |

---

## Key Decisions in Effect

- **ADR-010 / ADR-014 / ADR-015**: COLMAP 4.2.0 CUDA dense stereo pipeline with sequential matching (`overlap=10`, `quadratic_overlap=1`, `loop_detection=1`), `min_num_pixels=3` (turbo), and `--PoissonMeshing.trim 0`.
- **ADR-017 / ADR-018**: KDTree distance culling ($3.5 \times$ spacing), figure-8 cycle decomposition, and `float64` uniform scaling prior to binary STL export.
- **ADR-019 / ADR-022 / ADR-023**: Full-cloud RANSAC support plane alignment, camera-centroid upward polarity check, synchronous normal rotation, depth 10 Poisson on isolated cloud, SfM $<75\%$ circuit breaker, and anti-starburst $>60$ edge hole guard.

*Details in [`project/DECISIONS.md`](file:///home/synapse/Documents/LOOM/project/DECISIONS.md) and [`ARCHITECTURE.md`](file:///home/synapse/Documents/LOOM/ARCHITECTURE.md).*

---

## Immediate Next Task

1. Build Phase 2 API / Job Runner bridge (or run end-to-end physical caliper validation benchmark on arbitrary tabletop objects beyond footwear).
