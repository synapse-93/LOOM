# PROJECT CONTEXT — VIDEO2PRINT (LOOM)

**Project**: LOOM / VIDEO2PRINT  
**Objective**: Transition an ordinary smartphone video into a metrically scaled, validated, 3D printable object (.STL) with measurable manufacturing readiness.  
**Last Updated**: 2026-11-25  
**Current Iteration**: 035 (Milestone 1: 130-Keyframe Low-Texture SfM, All-Pose TSDF, Auto-Pruning Worker & `start_loom.sh`)  
**Current Milestone**: Milestone 1 Complete — 279/279 Tests Passing, `cube.mp4` 130/130 SfM & `bottle.mp4` Watertight STL Verified  

---

## Current Status Snapshot

| Dimension | Status | Notes |
| :--- | :--- | :--- |
| **Codebase State** | Milestone 1 Complete | Hardened COLMAP 4.2.0 SfM (`peak_threshold=0.002`, `edge_threshold=16`, `exhaustive_matcher <=150` with `--FeatureMatching.guided_matching 1` & `--SiftMatching.max_ratio 0.85`, `--Mapper.min_num_matches 10`, `--Mapper.init_min_num_inliers 50`). Raised default `max_frames` to `130` with `PipelineManifest.max_frames` cache invalidation. Upgraded 2DGS (`min_opacity=0.01`, `load_all_registered_poses` all-pose TSDF rendering with immediate CPU offload & `gt_mask=None` on excluded poses) and TSDF (`alpha_threshold=0.40`, `views_fused / total_registered_poses`). Added `/api/health` alias, `max_retained_jobs=5` SSD auto-pruning in `src/loom/web/manager.py`, and 1-command launcher `scripts/start_loom.sh`. |
| **Runtime Environment** | Linux / `.venv312` (CPython 3.12.16) | Active CUDA 13.0 ML/Geometry venv at `.venv312` (legacy `.venv` untouched). |
| **Dependencies & Hardware** | CUDA 13.0 Stack Verified | `torch 2.14.1+cu130`, `gsplat 1.5.3`, `rembg` (`isnet-general-use`), `open3d 0.20.0`, `trimesh`, `scipy`, `numpy`, `opencv-python`, `mapbox-earcut`, `fastapi`, `uvicorn`, `httpx`, `pytest`. Native `COLMAP 4.2.0` CUDA at `/usr/bin/colmap`, NVIDIA GeForce RTX 4060 Laptop GPU (8188 MiB VRAM, CUDA: True). |
| **Verification Status** | **279/279 passed** | `.venv312/bin/pytest tests/ -q` (`278 passed, 1 skipped` sandboxed) + `test_gsplat_153_cuda_shape_smoke PASSED` on RTX 4060. **`cube.mp4` SfM Gate** (`outputs/rewrite_cube_test`): **`130/130` (100.0%)**, `num_cameras=1`, `33,418` sparse pts (resolved prior `39/75` 5-island split). **`bottle.mp4` Full Exit Gate** (`outputs/rewrite_bottle_test`, `120.0 mm`): **`129/129` SfM/Masks/All-Pose TSDF**, 2DGS `final_loss=0.0091` (`240 MiB` VRAM), TSDF `557,539` verts / `1,088,268` faces, `loom_output.stl` **`92,600` verts / `187,036` faces**, **`PrintabilityGate PASSED`** (`watertight=True`, `manifold=True`, `13.33 cm³`, OBB `122.0×42.3×41.5 mm`, `Z_min=0.000000 mm`, exact `9,351,884` bytes). |
| **Active Blockers** | None | Zero-touch production launch ready via `./scripts/start_loom.sh`. |

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

1. Launch `./scripts/start_loom.sh` to start the RTX 4060 FastAPI worker + Cloudflare HTTPS tunnel and verify live upload/SSE streaming/STL download from `https://loomvidcapture.vercel.app`.
2. Finish the downstream stages (`--from-stage mask --export-stl`) on `outputs/rewrite_cube_test` if a full `cube.mp4` STL benchmark is desired alongside `box.mp4` and `bottle.mp4`.
