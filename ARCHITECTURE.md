# LOOM (VIDEO2PRINT) — System Architecture

**Objective:** Deterministic conversion of unconstrained tabletop smartphone video into a metrically scaled, watertight, 2-manifold, build-plate-flush binary STL ready for 3D printing.

---

## 1. End-to-End 8-Stage Pipeline (`--engine 2dgs` Default / `--engine colmap` Legacy)

```text
[ Smartphone Video (.mp4 / .webm / .mov) ]
              │
              ▼
 1. Video Ingest & Blur Filtering        src/loom/video/frames.py
    • Evenly strided keyframe sampling (130 standard / 68 in --turbo)
    • 8 GB VRAM cap: max(W, H) = 960 px standard / 720 px in --turbo (cv2.INTER_AREA)
    • Laplacian sharpness gating (variance >= 18.0)
              │
              ▼
 2. Sparse SfM, Circuit Breaker          src/loom/reconstruction/colmap.py
    & Image Undistortion                 src/loom/pipeline/manifest.py
    • Cache hygiene via pipeline_manifest.json (fast video SHA-256 + max_frames + resolution;
      wipes stale extracted_frames/, images/, database.db, sparse/, dense/, masks/, debug_*)
    • COLMAP 4.2.0 CUDA SIFT feature_extractor locked to single SIMPLE_RADIAL camera
      (--ImageReader.single_camera 1, --SiftExtraction.peak_threshold 0.002,
      --SiftExtraction.edge_threshold 16, max 8192)
    • Adaptive GPU matching: exhaustive_matcher (<= 150 images), sequential_matcher (> 150)
      with --FeatureMatching.guided_matching 1 and --SiftMatching.max_ratio 0.85
    • 16-thread mapper (--Mapper.min_num_matches 10, --Mapper.init_min_num_inliers 50)
      + largest numeric sparse/* model selection (asserting num_cameras == 1)
    • SfM Circuit Breaker: aborts with RuntimeError if registered views < 75% of keyframes
    • colmap image_undistorter on winning model -> dense/images/ + dense/sparse/ (PINHOLE)
              │
              ▼
 3. Unmasked Canonical Support Alignment src/loom/geometry/alignment.py
    • Full-cloud vectorized RANSAC support plane fit on UNMASKED COLMAP sparse points
    • Camera-Centroid Upward Gravity Polarity: asserts n · (C_cam - p0) > 0
      using camera centers C = -R^T t from dense/sparse/images.bin
    • Rodrigues SO(3) transform T_align mapping support normal n -> [0, 0, 1]^T at Z=0
              │
              ▼
 4. Semantic Foreground Masking          src/loom/reconstruction/masking.py
    & Multi-View Visual-Hull Filter      src/loom/reconstruction/visual_hull.py
    • Runs on UNDISTORTED images (dense/images/), never before Sparse SfM
    • Single reused rembg session (default: "isnet-general-use", configurable)
      with bounded CPU onnxruntime.SessionOptions (arena/mem_pattern disabled,
      4 intra / 1 inter threads), disk-resume skip, periodic gc.collect(), and
      explicit session release via masker.close() before 2DGS training
    • Alpha >= 128, 3x3 morphological open/close, retains central primary component
      (pruning islands < 1% image area) -> <workspace>/masks/*.png
    • View hygiene: valid if 2% <= coverage <= 95%; circuit breaker if <20 valid
      views; exports 4x4 visual audit sheet -> <workspace>/debug_masks/masks_grid.jpg
    • VisualHullFilter: strictly loads undistorted dense/sparse/{cameras,images,points3D}.bin,
      retains points with visible_count >= max(8, 0.20*N_valid) (fallback 5) and
      fg_hits/visible_count >= 0.70 (adaptive fallback 0.55 -> 0.40 if <500 survive),
      selects Open3D DBSCAN core cluster (eps=0.08*scene_radius, min_points=15, >=200 pts)
      closest to multi-view camera look-at convergence center (fallback median+2.0*MAD)
      -> tight object_center / object_radius & debug_masks/visual_hull_points.ply
              │
              ▼
 5. Masked 2D Gaussian Splatting (2DGS)  src/loom/reconstruction/gaussian_2dgs.py
    • Consumes manifest valid_views, visual_hull_points.ply, object_center, object_radius
    • gsplat 1.5.3 rasterization_2dgs(render_mode="RGB+ED", distloss=True, packed=False)
      (packed=False avoids upstream gsplat 1.5.3 packed SH bug; C=1 peak VRAM ~297 MiB)
    • Progressive SH 0 -> 2, exponential lr_means decay, random black/mid-gray/white BG
    • Composite Loss: 0.8*L1 + 0.2*(1-SSIM) + w_mask(step)*L1(alpha, mask)
      (w_mask: 0.5 first half -> linear decay to 0.05 second half to heal mask dropouts)
      + (step >= 1500) w_norm(step)*(1 - cos(render_n, surf_n))*mask (0.05 -> 0.08 final 30%)
      + 0.01*render_distort*mask
    • Adaptive densify/prune every 250 steps via info["gradient_2dgs"] (NDC-scaled)
      capped at max_gaussians = 150,000, min_opacity = 0.01; opacity reset at 3000 with cooldown
    • Exports 3 4-panel audit strips (<workspace>/debug_2dgs/view_{0,mid,last}.png:
      GT Masked RGB | Rendered RGB | Median Depth | Normals)
              │
              ▼
 6. Masked TSDF Fusion & Marching Cubes  src/loom/reconstruction/tsdf_mesh.py
    • Renders median depth (depth_mode="median") + RGB across ALL registered undistorted poses
      (immediate per-view GPU->CPU transfer under torch.no_grad(); gt_mask=None on excluded poses)
    • Filters background via 3D-consistent render_alpha >= 0.40 (skipping noisy 2D gt_mask
      clipping when render_alpha is present so mask dropouts never re-punch wall voids)
    • Tight surfel bounding sphere (opacity > 0.35, DBSCAN + 5th-95th pct, <= 1.35*object_radius):
      voxel_length = max(tight_radius / 320, 1e-4), sdf_trunc = 2.5 * voxel_length,
      depth clip [0.05, cam_dist + 1.5 * tight_radius], logs View 0 Z-depth audit
    • Open3D sparse VoxelBlockGrid TSDF (CPU) -> extract_triangle_mesh() -> largest cluster
      -> <workspace>/mesh_2dgs_raw.ply -> transformed by T_align
              │
              ▼
 7. Taubin Polish, Watertight            src/loom/mesh/processor.py , src/loom/scaling/ ,
    Solidification & Metric Scaling      scripts/demo.py
    • Feature-preserving Taubin smoothing (5 iters, lambda=0.5, mu=-0.53)
    • Planar base slice (2nd pct Z) + mapbox-earcut flat cap -> Tier 1 hole repair ->
      Tier 2 Open3D Screened Poisson (depth=9, scale=1.25) / 180-voxel + Taubin + flat cap
      guaranteeing watertight 2-manifold positive-volume solid
    • Quadric decimation (>200k -> 150k faces, kept only if PrintabilityGate holds)
    • Uniform float64 scaling to --target-length (default 200.0 mm), Z_min = 0.000 mm,
      centered at (X=0, Y=0)
              │
              ▼
 8. Printability Gate & Binary STL       src/loom/printability/gate.py
    Export with Cryptographic Manifest   src/loom/export/stl.py
    • PrintabilityGate enforces: watertight (0 boundary edges), 2-manifold
      (0 non-manifold edges/vertices), consistent outward normals, volume > 0
    • Binary STL export (<workspace>/loom_output.stl) verified against 84 + 50 * N_faces
    • Companion <workspace>/printability_manifest.json + pipeline_manifest.json export block
```

*(Legacy classical backend remains available via `--engine colmap`: COLMAP `patch_match_stereo` -> `stereo_fusion` -> pre-mesh RANSAC + cylindrical crop -> `poisson_mesher` depth 10 / `trim=0`.)*

---

## 2. Module Boundaries & Responsibilities

| Package | Responsibility | Strictly Prohibited |
| :--- | :--- | :--- |
| `src/loom/video/` | Video validation, frame striding, `cv2.INTER_AREA` downscaling, Laplacian blur filtering | Reconstruction logic, mesh I/O |
| `src/loom/capture/` | Frame sharpness, exposure, redundancy, and capture coverage metrics | Subprocess execution |
| `src/loom/reconstruction/` | Interchangeable photogrammetry adapters (`ReconstructionEngine` ABC: `ColmapAdapter`, `MeshroomAdapter`) | Hardcoded object assumptions, STL export |
| `src/loom/geometry/` | Binary PLY normal I/O, full-cloud RANSAC alignment, Rodrigues $SO(3)$ rotation, camera polarity, foreground segmentation | Reconstruction CLI coupling |
| `src/loom/mesh/` | Diagnostics, KDTree distance culling, connected component filtering, `mapbox-earcut` planar base capping, hole repair | External binary calls |
| `src/loom/scaling/` | ArUco fiducial detection, COLMAP sparse model parsing, multi-view triangulation, uniform mesh scaling | Hardcoded object lengths |
| `src/loom/validation/` | AABB/OBB principal dimension measurement and ground-truth error comparison | Mesh mutation |
| `src/loom/printability/` | Watertightness, 2-manifoldness, overhang, wall thickness, and `PrintabilityGate` enforcement | Silent defect suppression |
| `src/loom/export/` | Validated binary STL writer and JSON build manifest generation | Mesh geometry repair |
| `src/loom/utils/` | Path normalization, SHA-256 hashing, logging, and CUDA-aware subprocess execution (`subprocess.py`) | Pipeline business logic |
| `src/loom/web/` | FastAPI local GPU worker (`app.py`), single-GPU FIFO queue (`manager.py`), typed schemas (`models.py`), SSE live log bridge | Direct mesh mutation or concurrent GPU jobs |

---

## 2.5. Local GPU Worker & Vercel Bridge API (`src/loom/web/`)

Launched via `scripts/serve_worker.py` (`uvicorn loom.web.app:app`) and exposed over HTTPS to `https://loomvidcapture.vercel.app` via `cloudflared tunnel --url http://localhost:8000`:

| Endpoint | Method | Contract |
| :--- | :--- | :--- |
| `/health` | `GET` | Probes `nvidia-smi` and `colmap -h` via `run_subprocess`; returns GPU VRAM, COLMAP version, active job, queue depth, `ready`. |
| `/api/reconstruct` | `POST` | Streams `.mp4`/`.webm`/`.mov` (<=500 MB) in 1 MB chunks to `outputs/web_jobs/<job_id>/`, optionally remuxes `.webm` via `ffmpeg`, enqueues into strict 1-at-a-time `asyncio.Queue` GPU FIFO worker; returns `202 Accepted`. |
| `/api/jobs` | `GET` | Lists all `JobSummary` records sorted newest first. |
| `/api/jobs/{job_id}` | `GET` | Returns `JobSummary` (`404` if unknown). |
| `/api/jobs/{job_id}/stream` | `GET` | `text/event-stream` (`Cache-Control: no-cache`, `X-Accel-Buffering: no`); replays buffered logs (max 2000 lines), fans out live `event: log` & `event: progress`, emits 15s heartbeats, closes with `event: done`. |
| `/api/jobs/{job_id}/stl` | `GET` | Downloads verified binary `.stl` (`application/octet-stream`; `409` if incomplete, `404` if missing). |
| `/api/jobs/{job_id}/manifest` | `GET` | Returns parsed JSON manifest (`409` if incomplete, `404` if missing). |
| `/api/jobs/{job_id}` | `DELETE` | Cancels queued/active job (`terminate()` -> 5s -> `kill()`) or deletes a terminal job record. |

---

## 3. Core Geometric & Runtime Invariants

1. **No Camera-Axis Elevation Bias:** Support plane RANSAC runs over the entire point cloud (sampled up to 60,000 points), never slicing by raw camera-frame Z, guaranteeing invariance to arbitrary handheld tilt.
2. **Gravity Polarity Ground Truth:** When `sparse/0/images.bin` camera centers $\mathbf{C}_{\text{cam}}$ are present, the plane normal $\mathbf{n}$ is guaranteed to satisfy $\mathbf{n} \cdot (\mathbf{C}_{\text{cam}} - \mathbf{p}_0) > 0$.
3. **Synchronous Vertex & Normal Rotation:** Poisson reconstruction requires outward-consistent vertex normals `(nx, ny, nz)`. Both vertex coordinates and unit normal vectors rotate synchronously under the same $SO(3)$ matrix $R$.
4. **Closed Poisson Zero-Crossing:** `--PoissonMeshing.trim 0` is locked so Poisson produces a watertight shell prior to controlled planar base slicing at $Z = 0.005$.
5. **SfM Tracking Circuit Breaker:** Sparse mapping aborts immediately with `RuntimeError` if fewer than 75% of input frames register in `images.bin`, preventing downstream starburst artifacts on incomplete orbits.
6. **CUDA Dynamic Linker Isolation:** `src/loom/utils/subprocess.py` automatically prepends `/opt/cuda/lib64` to `LD_LIBRARY_PATH` whenever present on the host so `/usr/bin/colmap` resolves `libcudart.so.*` reliably.
7. **Zero Heavyweight ML Dependencies:** The core pipeline relies strictly on `numpy`, `scipy`, `trimesh`, `mapbox-earcut`, `opencv-python`, `pyyaml`, and native COLMAP 4.2.0 CUDA; `open3d` remains strictly optional.

