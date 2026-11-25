# PROJECT CONTEXT — VIDEO2PRINT (LOOM)

**Project**: LOOM / VIDEO2PRINT  
**Objective**: Transition an ordinary smartphone video into a metrically scaled, validated, 3D printable object (.STL) with measurable manufacturing readiness.  
**Last Updated**: 2026-11-25  
**Current Iteration**: 036 (Milestone 3A: Production Tunnel Hardening & QR Auto-Pairing)  
**Current Milestone**: Milestone 3A Complete — 280 passed (+1 CUDA smoke) / Root Route, CORS Preflight, SSE Keepalive & QR Auto-Pairing Verified  

---

## Current Status Snapshot

| Dimension | Status | Notes |
| :--- | :--- | :--- |
| **Codebase State** | Milestone 3A Complete | Hardened FastAPI worker (`GET /` service route, explicit Vercel + localhost CORS preflight, SSE `Cache-Control: no-cache` / `Connection: keep-alive` / `X-Accel-Buffering: no` + 15s `: keepalive\n\n` comments) and `scripts/start_loom.sh` (`SHUTTING_DOWN=0` idempotent trap guard, URL-encoded pre-paired link `https://loomvidcapture.vercel.app/?worker=...`, and terminal QR code via `qrcode` or `/usr/bin/qrencode`). Builds cleanly on Milestone 1 (`130`-keyframe low-texture SfM, all-pose TSDF, `max_retained_jobs=5` pruning). |
| **Runtime Environment** | Linux / `.venv312` (CPython 3.12.16) | Active CUDA 13.0 ML/Geometry venv at `.venv312` (legacy `.venv` untouched). |
| **Dependencies & Hardware** | CUDA 13.0 Stack Verified | `torch 2.14.1+cu130`, `gsplat 1.5.3`, `rembg` (`isnet-general-use`), `open3d 0.20.0`, `trimesh`, `scipy`, `numpy`, `opencv-python`, `mapbox-earcut`, `fastapi`, `uvicorn`, `httpx`, `pytest`. Native `COLMAP 4.2.0` CUDA at `/usr/bin/colmap`, `/usr/bin/qrencode`, NVIDIA GeForce RTX 4060 Laptop GPU (8188 MiB VRAM, CUDA: True). |
| **Verification Status** | **280 passed, 1 skipped (sandbox)** | `.venv312/bin/pytest tests/ -q` (`280 passed, 1 skipped` sandboxed; `test_api.py` covers `GET /`, Vercel/localhost CORS preflight, SSE headers & `: keepalive\n\n` emission) + `bash -n scripts/start_loom.sh` passed. Milestone 1 empirical gates remain verified (`cube.mp4` `130/130` SfM; `bottle.mp4` `129/129` SfM -> watertight `loom_output.stl`). |
| **Active Blockers** | None | Zero-touch production launch + QR auto-pairing ready via `./scripts/start_loom.sh`. |

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
