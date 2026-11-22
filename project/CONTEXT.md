# PROJECT CONTEXT — VIDEO2PRINT (LOOM)

**Project**: LOOM / VIDEO2PRINT  
**Objective**: Transition an ordinary smartphone video into a metrically scaled, validated, 3D printable object (.STL) with measurable manufacturing readiness.  
**Last Updated**: 2026-11-22  
**Current Iteration**: 034 (Rewrite Phase 4 Final: Void-Elimination 2DGS/TSDF, Guaranteed Watertight Export & `.venv312` FastAPI Worker)  
**Current Milestone**: All 4 Architectural Rewrite Phases Complete — 277/277 Tests Passing & End-to-End Watertight `box.mp4` STL Verified  

---

## Current Status Snapshot

| Dimension | Status | Notes |
| :--- | :--- | :--- |
| **Codebase State** | All 4 Rewrite Phases Complete | Applied void-elimination fixes in `gaussian_2dgs.py` (`lambda_mask` `0.5->0.05` second-half decay, `lambda_normal` `0.05->0.08` final 30%) and `tsdf_mesh.py` (`render_alpha>=0.45` without re-punching `gt_mask` voids, `voxel_divisor=320`, `trunc=2.5`). Extended `PipelineManifest` with `export` dict & `"export"` stage gate/resume. Implemented `MeshProcessor.solidify_for_print()` (Taubin polish, 2nd-pct planar base cap, Tier 1 hole fill, Tier 2 Screened Poisson + 180-voxel/Taubin/flat-cap watertight guarantee, quadric decimation, `float64` scaling, `Z_min=0`). Wired `--engine 2dgs --export-stl`, `<workspace>/loom_output.stl`, and `[VISUAL_HULL]`/`[EXPORT]` SSE progress into `src/loom/web/manager.py` & `scripts/serve_worker.py`. |
| **Runtime Environment** | Linux / `.venv312` (CPython 3.12.16) | Active CUDA 13.0 ML/Geometry venv at `.venv312` (legacy `.venv` untouched). |
| **Dependencies & Hardware** | CUDA 13.0 Stack Verified | `torch 2.14.1+cu130`, `gsplat 1.5.3`, `rembg` (`isnet-general-use`), `open3d 0.20.0`, `trimesh`, `scipy`, `numpy`, `opencv-python`, `mapbox-earcut`, `fastapi`, `uvicorn`, `httpx`, `pytest`. Native `COLMAP 4.2.0` CUDA at `/usr/bin/colmap`, NVIDIA GeForce RTX 4060 Laptop GPU (8188 MiB VRAM, CUDA: True). |
| **Verification Status** | **277/277 passed** | `.venv312/bin/pytest tests/ -q` (`276 passed, 1 skipped` sandboxed) + `test_gsplat_153_cuda_shape_smoke PASSED` on RTX 4060. Full-res `box.mp4` Phase 4 end-to-end exit gate (`outputs/rewrite_box_test`): 2DGS `77,986` surfels (`298 MiB` peak VRAM) -> TSDF `455,305` verts / `877,533` faces (`voxel=0.00683`) -> `loom_output.stl` **`95,173` verts / `192,902` faces**, **`PrintabilityGate PASSED`** (`watertight=True`, `manifold=True`, `0` boundary/non-manifold edges, `56.62 cm³`, `[154.92, 200.00, 85.95] mm`, `Z_min=0.000000 mm`, exact `9,645,184` bytes). |
| **Active Blockers** | None | Production-ready for live FastAPI worker (`scripts/serve_worker.py`) + Vercel frontend bridge. |

---

## Pipeline Component Status

| Pipeline Stage | Module Path | Status | Verified? |
| :--- | :--- | :--- | :--- |
| **1. Video Ingest & Filtering** | `src/loom/video/` | **COMPLETE** | Yes (960px std / 720px turbo, 68 turbo frames, Laplacian $\tau=18.0$) |
| **2. Sparse SfM & Undistortion** | `src/loom/reconstruction/colmap.py` | **COMPLETE** | Yes (COLMAP 4.2.0 CUDA, sequential overlap 10, $<75\%$ SfM circuit breaker) |
| **3. Semantic Foreground Masking** | `src/loom/reconstruction/masking.py` | **COMPLETE** | Yes (`isnet-general-use` default, bounded ONNX CPU `SessionOptions`, resume skip, `close()` RAM cleanup) |
| **4. Masked 2DGS Optimizer** | `src/loom/reconstruction/gaussian_2dgs.py` | **COMPLETE** | Yes (`gsplat 1.5.3` `rasterization_2dgs`, mask + SSIM + post-1500 normal/dist loss, 150k cap) |
| **5. Masked Sparse TSDF Mesher** | `src/loom/reconstruction/tsdf_mesh.py` | **COMPLETE** | Yes (Open3D `VoxelBlockGrid` CPU sparse TSDF, adaptive $R/256$ voxel, largest cluster) |
| **6. Canonical Alignment & Repair** | `src/loom/geometry/`, `src/loom/mesh/` | **COMPLETE** | Yes (Unmasked sparse RANSAC + camera-centroid polarity, `mapbox-earcut` base cap) |
| **7. Scaling, Gate & STL Export** | `src/loom/scaling/`, `printability/`, `export/` | **COMPLETE** | Yes (ArUco / float64 `--target-length`, $Z_{\min}=0$, `PrintabilityGate`, binary STL + manifest) |
| **8. Local GPU Worker & Bridge** | `src/loom/web/`, `scripts/serve_worker.py` | **COMPLETE** | Yes (8 REST/SSE endpoints, `[MASK]`/`[2DGS]`/`[TSDF]` progress tracking, 1-job FIFO queue) |

---

## Key Decisions in Effect

- **ADR-010 / ADR-014 / ADR-023**: COLMAP 4.2.0 CUDA Sparse SfM (`overlap=10`, `quadratic_overlap=1`, `loop_detection=1`), $<75\%$ SfM circuit breaker, and anti-starburst $>60$ edge hole guard.
- **Masked 2DGS + Sparse TSDF Engine**: `isnet-general-use` masking (`dense/images/`) -> DBSCAN `VisualHullFilter` -> Masked `gsplat 1.5.3` `rasterization_2dgs` (`packed=False`, `gradient_2dgs` NDC densification, `lambda_dist=0.01`, 150k cap, peak ~297 MiB VRAM) -> Open3D `VoxelBlockGrid` CPU sparse TSDF (avoiding Open3D 0.20.0 legacy `ScalableTSDFVolume` 0-face regression). Legacy `--engine colmap` remains available.
- **Web Worker Bridge**: FastAPI + `uvicorn` single-GPU `asyncio.Queue` FIFO worker isolating per-job artifacts under `outputs/web_jobs/<job_id>/` and streaming SSE events to `https://loomvidcapture.vercel.app`.

*Details in [`project/DECISIONS.md`](file:///home/synapse/Documents/LOOM/project/DECISIONS.md) and [`ARCHITECTURE.md`](file:///home/synapse/Documents/LOOM/ARCHITECTURE.md).*

---

## Immediate Next Task

1. Launch `.venv312/bin/python scripts/serve_worker.py` + `cloudflared tunnel --url http://localhost:8000` and run a live upload from `https://loomvidcapture.vercel.app` to verify end-to-end SSE streaming and `.stl` download in the browser.
2. Benchmark additional diverse tabletop objects (e.g., shoes, mugs, figurines) through `--engine 2dgs --turbo --export-stl` to validate cross-object generalization and turnaround time.
