# ITERATION CHANGELOG — VIDEO2PRINT

This log records chronological development iterations. Every agent completing meaningful work must add an entry following this format.

---

## Iteration 034 — Architectural Rewrite Phase 4 (Final): Void-Elimination 2DGS/TSDF, Guaranteed Watertight Export & `.venv312` FastAPI Worker
- **Date**: 2026-11-22
- **Milestone**: All 4 Architectural Rewrite Phases Complete (277/277 Tests Passing + End-to-End Watertight `box.mp4` STL Verified)
- **Changes Implemented**:
  - **Void-Elimination Fixes (`src/loom/reconstruction/gaussian_2dgs.py`, `src/loom/reconstruction/tsdf_mesh.py`)**:
    - Added `scheduled_lambda_mask()` (`0.5` for steps `1..50%`, linearly decaying to `0.05` over the second half of training so multi-view RGB + normal consistency heals per-frame `isnet` mask dropouts) and `scheduled_lambda_normal()` (`0.05 -> 0.08` over the final 30% of training to flatten planar micro-ripple).
    - Updated `TsdfExtractionConfig` to `voxel_divisor=320.0`, `trunc_voxel_multiplier=2.5`, `alpha_threshold=0.45`, and updated `mask_depth_map()` to filter background via converged 3D-consistent `render_alpha >= 0.45` (skipping noisy 2D `gt_mask` clipping when `render_alpha` is present, with configurable `21x21` dilation fallback).
  - **Manifest `export` Contract & Stage Gate (`src/loom/pipeline/manifest.py`, `scripts/demo.py`)**:
    - Added backward-compatible `export: dict` field (`stl_path`, `manifest_path`, `vertices`, `faces`, `is_watertight`, `is_winding_consistent`, `volume_cm3`, `extents_mm`, `z_min_mm`, `solidification_method`) and extended `invalidate_from_stage`, `--from-stage`, and `--stop-after` with `"export"` (supporting direct resume from cached `mesh_2dgs_raw.ply`).
  - **Canonical Alignment, Taubin Polish & Guaranteed Watertight Export (`src/loom/mesh/processor.py`, `scripts/demo.py`)**:
    - Implemented `MeshProcessor.solidify_for_print()` returning `SolidificationResult`: largest-component cleanup, Open3D Taubin smoothing (`5` iters, `lambda=0.5`, `mu=-0.53`), 2nd-percentile planar base cut & `mapbox-earcut` flat cap (`"planar_cap"`), Tier 1 hole fill + winding/normal repair (`"hole_fill"`), Tier 2 Open3D Screened Poisson (`depth=9, scale=1.25`) / high-res `180`-voxel + Taubin + flat base cap watertight guarantee (`"voxel_remesh"`), Open3D quadric decimation (`>200k -> 150k` faces, kept only if `PrintabilityGate` holds), uniform `float64` scaling to `--target-length`, `Z_min = 0.000 mm`, X/Y centering, and `PrintabilityGate`-enforced binary `<workspace>/loom_output.stl` + `<workspace>/printability_manifest.json` export.
  - **FastAPI Worker Integration (`src/loom/web/manager.py`, `scripts/serve_worker.py`)**:
    - Updated `infer_stage_and_progress()` to track `[MASK]`, `[VISUAL_HULL]`, `[2DGS] Step X/Y`, `[TSDF]`, and `[EXPORT]` / `PrintabilityGate` markers across `0–100%`.
    - Wired `manager.py` to launch `scripts/demo.py` via `sys.executable` with `--engine 2dgs --export-stl` and resolve `<workspace>/loom_output.stl` & `<workspace>/printability_manifest.json` cleanly in `_discover_artifacts()`.
  - **Unit Tests**:
    - Added `tests/unit/mesh/test_watertight_solidification.py` (open-bottom + side-hole box and open-bottom cylinder solidification tests).
    - Updated `tests/unit/reconstruction/test_tsdf_mesh.py`, `test_gaussian_2dgs.py`, and `tests/unit/web/test_api.py`.
- **Verification**:
  - `.venv312/bin/pytest tests/ -q`: **276 passed, 1 skipped** (sandboxed) + `test_gsplat_153_cuda_shape_smoke PASSED` on RTX 4060 (**277/277 total**).
  - Full-resolution (`540×960`, `turbo=False`) end-to-end exit gate on `/home/synapse/Downloads/box.mp4` (`outputs/rewrite_box_test`):
    - 2DGS (7,000 iters, 60 valid views, void-elimination schedules): `11,281 -> 77,986` surfels, `final_loss = 0.1000`, **peak VRAM `298.2 MiB`**.
    - TSDF (`voxel_divisor=320`, `trunc=2.5`, `alpha>=0.45`): **`455,305` verts / `877,533` faces** (`tight_radius = 2.1855`, `voxel_length = 0.006830`) in `4.55s`.
    - Export (`loom_output.stl` + `printability_manifest.json`): **`95,173` verts / `192,902` faces**, `solidification_method = "voxel_remesh"`, **`PrintabilityGate PASSED`** (`is_watertight = True`, `is_manifold = True`, `0` boundary edges, `0` non-manifold edges/verts, `volume = 56.62 cm³`, `extents = [154.919, 200.000, 85.948] mm`, `Z_min = 0.000000 mm`, exact `9,645,184` bytes = `84 + 50 * 192902`).

---

## Iteration 033 — Architectural Rewrite Phase 3: DBSCAN Visual-Hull Core, Manifest-Driven 2DGS (`gsplat 1.5.3`) & Tight Sparse TSDF
- **Date**: 2026-11-22
- **Milestone**: Rewrite Phase 3 Complete (275/275 Tests Passing + Full-Res `box.mp4` 2DGS + TSDF Exit Gate Visually Verified)
- **Changes Implemented**:
  - **Visual-Hull Core Tightening (`src/loom/reconstruction/visual_hull.py`)**:
    - Raised multi-view visibility gate to `max(8, int(0.20 * num_valid_views))` (fallback `5`).
    - Added `compute_camera_lookat_center()` (least-squares optical-axis convergence center) and Open3D `cluster_dbscan` core selection (`eps = 0.08 * scene_radius`, `min_points = 15`, selecting largest dense cluster `>= 200` pts closest to look-at center, with `median + 2.0 * MAD` fallback) plus `read_colored_ply()`.
  - **Manifest Contracts & Stage Invalidation (`src/loom/pipeline/manifest.py`, `scripts/demo.py`)**:
    - Extended `PipelineManifest` with `gaussian_2dgs: dict`, `tsdf: dict`, and `invalidate_from_stage(stage)`.
    - Wired `--from-stage {frames,sfm,undistort,mask,visual_hull,2dgs,tsdf}` and extended `--stop-after` to `{sfm,mask,visual_hull,2dgs,tsdf}` in `scripts/demo.py` with clean stage-resume reuse for `mask` and `visual_hull`.
  - **Rewrote Masked 2DGS Optimizer (`src/loom/reconstruction/gaussian_2dgs.py`)**:
    - Consumes `valid_views`, `debug_masks/visual_hull_points.ply`, `object_center`, and `object_radius` directly from `pipeline_manifest.json`.
    - Fixed two critical `gsplat 1.5.3` bugs caught by the Phase 3 visual audit:
      1. `info["means2d"].grad` is identically `0.0` in `rasterization_2dgs`; switched densification accumulation to `info["gradient_2dgs"].grad` with NDC screen-space scaling (`width/2`, `height/2`) over visible surfels `sel = (info["radii"] > 0.0).all(dim=-1)`.
      2. `gsplat 1.5.3` computes L1 world-space distortion (`render_distort`), NOT Inria's squared NDC distortion; `lambda_dist = 100.0` caused a 106× loss spike (`4.836`) at step 1500 that collapsed surfels from `11,030 -> 68`. Set `lambda_dist = 0.01` (foreground-masked), kept `lambda_normal = 0.05` (empirically verified `cos(render_normals, surf_normals) == +1.0`), added in-place parent scale shrinkage on split, prioritized highest-gradient cloning/splitting under `max_gaussians = 150,000`, set `opacity_reset_interval = 3000` with a 1-interval post-reset prune cooldown, and added exponential `lr_means` decay (`1.6e-4 -> 1.6e-6 * object_radius`).
    - Upgraded `compose_debug_panel()` and `save_debug_renders()` to 4-panel convergence strips (`<workspace>/debug_2dgs/view_{0,mid,last}.png`: `[GT Masked RGB | Rendered RGB | Colorized Median Depth | Rendered Normals]`).
  - **Rewrote Tight Sparse TSDF Extractor (`src/loom/reconstruction/tsdf_mesh.py`)**:
    - Computes tight surfel bounding sphere from `opacity > 0.35` surfels via DBSCAN + 5th–95th percentile trimming clamped to `<= 1.35 * object_radius`.
    - Sets `voxel_length = max(tight_radius / 256.0, 1e-4)`, `sdf_trunc = 3.0 * voxel_length`, depth clip `[0.05, cam_dist + 1.5 * tight_radius]`, logs View 0 Z-depth audit (`min/median/max/cam_dist`), integrates via Open3D `VoxelBlockGrid` (CPU), keeps largest connected component, and writes `<workspace>/mesh_2dgs_raw.ply` + `tsdf` manifest telemetry.
  - **Unit & CUDA Smoke Tests (`tests/unit/reconstruction/test_visual_hull.py`, `test_gaussian_2dgs.py`, `test_tsdf_mesh.py`)**:
    - Added DBSCAN fringe-cluster pruning test, updated 4-panel and `min_opacity=0.35` tests, and added real RTX 4060 `test_gsplat_153_cuda_shape_smoke` verifying `info["gradient_2dgs"].grad.abs().sum() > 0`.
- **Verification**:
  - `.venv312/bin/pytest tests/ -q`: **274 passed, 1 skipped** (sandboxed) + `test_gsplat_153_cuda_shape_smoke PASSED` on RTX 4060 (**275/275 total**).
  - Full-resolution (`540×960`, `turbo=False`) real-video exit gate on `/home/synapse/Downloads/box.mp4` (`outputs/rewrite_box_test`, `--from-stage 2dgs --stop-after tsdf`):
    - Visual Hull (DBSCAN, `vis>=12`, `ratio>=0.70`): `20,002 -> 11,281` core points, `object_radius = 1.8612` vs `scene_radius = 3.8784`.
    - 2DGS (7,000 iters, 60 valid views): `11,281 -> 79,044` surfels, loss down to `0.0150` at step 6500 (`0.1378` on step 7000 view), **peak VRAM = 297.2 MiB**, `284.66s`.
    - Visual Audit (`debug_2dgs/view_{0,mid,last}.png`): legible fine print on box walls, smooth planar depth & normals, multi-view rejection of leaked background cloth in `view_mid.png` and mask-hole completion in `view_last.png`.
    - Sparse TSDF (`VoxelBlockGrid` CPU, 60 views): `tight_radius = 2.1901`, `voxel_length = 0.008555`, `sdf_trunc = 0.025665`, **293,020 vertices / 563,954 faces**, `extents = [1.7390, 3.6068, 3.0713]` in **3.12s** -> `outputs/rewrite_box_test/mesh_2dgs_raw.ply`.

---

## Iteration 032 — Architectural Rewrite Phase 2: Memory-Safe Masking, Visual-Hull Filter & Visual Audit Gates
- **Date**: 2026-11-22
- **Milestone**: Rewrite Phase 2 Complete (273/273 Tests Passing + Full-Res `box.mp4` Visual-Hull Gate Verified)
- **Changes Implemented**:
  - **Extended `PipelineManifest` (`src/loom/pipeline/manifest.py`)**: Added backward-compatible `masking: dict` and `visual_hull: dict` fields recording valid/excluded views, median coverage, contact sheet path, foreground point count, ratio threshold used, `object_center`, `object_radius`, `scene_radius`, and `filtered_ply_path`.
  - **Hardened `ForegroundMasker` (`src/loom/reconstruction/masking.py`)**:
    - Enforced `isnet-general-use` default with bounded CPU ONNX `SessionOptions` (`enable_cpu_mem_arena=False`, `enable_mem_pattern=False`, `intra_op_num_threads=4`, `inter_op_num_threads=1`, `CPUExecutionProvider`), disk resume, periodic `gc.collect()`, and `close()`.
    - Added view hygiene classification (`0.02 <= coverage <= 0.95` valid vs `empty_or_tiny` / `over_segmented` excluded) with `< 20` valid-view circuit breaker (`>= 60%` when total views `< 20`).
    - Added `build_mask_contact_sheet()` generating a 4×4 `debug_masks/masks_grid.jpg` audit sheet with `#10B981` green contours on valid views and red borders + `"EXCLUDED (X.X%)"` tags on up to 4 excluded views.
  - **Created `VisualHullFilter` (`src/loom/reconstruction/visual_hull.py`)**:
    - Strictly loads undistorted `PINHOLE` cameras, poses, and 3D points from `dense/sparse/{cameras,images,points3D}.bin`.
    - Performs true multi-view silhouette intersection (`visible_count >= 5`, `fg_hits / visible_count >= 0.70`, adaptive fallback `0.55 -> 0.40` if `< 500` survive) + `median + 2.5 * MAD` outlier pruning.
    - Computes tight `object_center`, `object_radius` (95th percentile), and `scene_radius`, exporting `<workspace>/debug_masks/visual_hull_points.ply`.
  - **Stage Gate Integration (`scripts/demo.py`)**: Added `--stop-after {sfm,mask,visual_hull}` (preserving `--sfm-only` alias), wired `ForegroundMasker` -> `masker.close()` -> `VisualHullFilter` -> manifest persistence, and printed Phase 2 summary telemetry.
  - **Unit Tests (`tests/unit/reconstruction/test_masking.py`, `test_visual_hull.py`)**: Added tests for view hygiene, `< 20` circuit breaker, 4×4 contact sheet generation, and multi-view `>= 70%` background wall rejection.
- **Verification**:
  - `.venv312/bin/pytest tests/ -q`: **273 passed, 2 warnings in 9.43s** (0 failures, 0 errors).
  - Full-resolution (`540×960`, `turbo=False`) real-video exit gate on `/home/synapse/Downloads/box.mp4` (`outputs/rewrite_box_test`):
    - Cache invalidation cleanly purged previous 720p turbo cache on `turbo: True -> False`.
    - SfM: **74 / 74 views (100.0%)**, `num_cameras = 1`, **20,002 sparse points**.
    - Masking (`isnet-general-use`, zero OOM): **60 / 74 valid views**, 14 excluded (`empty_or_tiny`), median coverage **33.9%**, `masks_grid.jpg` generated.
    - Visual Hull: **20,002 → 11,306 foreground points** (`ratio >= 0.70` in `0.16s`), `object_radius = 1.8607` vs `scene_radius = 3.8789`, `visual_hull_points.ply` exported.
    - Total turnaround: **120.49s**.

---

## Iteration 031 — Architectural Rewrite Phase 1: Pipeline Manifest, Cache Hygiene & Hardened Single-Camera COLMAP SfM
- **Date**: 2026-11-22
- **Milestone**: Rewrite Phase 1 Complete (271/271 Tests Passing + `box.mp4` 67/67 Single-Camera Exit Gate)
- **Changes Implemented**:
  - **Typed Pipeline Manifest & Cache Hygiene (`src/loom/pipeline/manifest.py`, `src/loom/pipeline/__init__.py`)**:
    - Added `@dataclass PipelineManifest` persisted atomically to `<workspace>/pipeline_manifest.json` (`video_path`, fast head/tail 1 MB `video_sha256`, `engine`, `turbo`, `frame_resolution`, `sfm` metrics dict, `stages_completed`).
    - Implemented `prepare_workspace()` automatically purging stale `extracted_frames/`, `images/`, `database.db`, `sparse/`, `dense/`, `masks/`, and `debug_*` whenever `pipeline_manifest.json` is missing, `video_sha256` changes, `turbo` flips, or on-disk frame resolution mismatches `frame_resolution`; resumes completed stages safely when hashes and resolutions match.
  - **Hardened Single-Camera COLMAP Sparse SfM (`src/loom/reconstruction/colmap.py`)**:
    - Locked `feature_extractor` to `--ImageReader.camera_model SIMPLE_RADIAL`, `--ImageReader.single_camera 1`, `--SiftExtraction.peak_threshold 0.004`, `--SiftExtraction.max_num_features 8192`, `--FeatureExtraction.use_gpu 1 --FeatureExtraction.gpu_index <gpu_index>`.
    - Implemented adaptive GPU matching: `exhaustive_matcher` (`--FeatureMatching.use_gpu 1`) when `num_images <= 120`, falling back to `sequential_matcher` (`overlap=10`, `quadratic_overlap=1`, `loop_detection=1`) only when `num_images > 120`.
    - Added `select_largest_sparse_model()` scanning all numeric `sparse/*` subdirectories, picking max registered views, asserting `num_cameras == 1` (logging loud warning on violation), and routing the winning model to the `< 75%` SfM circuit breaker and `image_undistorter`.
    - Added `extract_sparse_scene_metadata()` exposing unmasked sparse points and camera centers from the winning model for Phase 2/4 reuse.
  - **Orchestrator Wiring & Banner (`scripts/demo.py`)**:
    - Wired `prepare_workspace()`, `"frames"`/`"sfm"`/`"undistort"` manifest recording, optional `--sfm-only` gate flag, and accurate `Engine: Masked 2DGS + TSDF` startup banner.
  - **Unit Tests (`tests/unit/pipeline/test_manifest.py`, `tests/unit/reconstruction/test_colmap_adapter.py`)**:
    - Added cache wipe/resume tests, optical-lock flag assertions, adaptive `<= 120` vs `> 120` matcher routing, and multi-model `sparse/*` winner selection tests.
- **Verification**:
  - `.venv312/bin/pytest tests/ -q`: **271 passed, 2 warnings in 11.98s** (0 failures, 0 errors).
  - Live `box.mp4` SfM-only verification (`outputs/rewrite_box_test`): **67 / 67 views (100.0%)**, **`num_cameras = 1`**, **11,205 sparse points**, `frame_resolution = [405, 720]`, total **23.78s** (Frames: 4.64s, SfM: 18.86s, Undistort: 0.27s).

---

## Iteration 030 — Visual-Hull Point Filtering, Tight Object TSDF Bounds & 2DGS Diagnostic Renders
- **Date**: 2026-11-22
- **Milestone**: 2DGS Geometry Precision & Diagnostic Tooling (267/267 Tests Passing)
- **Root Cause**:
  - Previous sparse point filter (`fg_hits >= 2`) retained 99.4% of background room points that briefly passed behind the object mask, inflating `scene_radius` ~7.6x (`3.947` vs actual object `~0.52`), overshooting `lr_means` ~10x, and making TSDF voxels ~15x too coarse.
- **Changes Implemented**:
  - **True Multi-View Visual-Hull Filter (`src/loom/reconstruction/gaussian_2dgs.py`)**:
    - Projects sparse 3D points across all valid-mask cameras (`2% <= coverage <= 95%`), retaining points with `visible_count >= 5` AND `fg_hits / visible_count >= 0.70` (iteratively relaxing to `0.55`, then `0.40` if `< 500` points survive).
    - Computes `object_center` (median) and `object_radius` (95th percentile distance from median) strictly from filtered foreground points and scales `lr_means` and surfel split/prune thresholds by `object_radius`.
  - **Tight High-Opacity TSDF Bounding Sphere (`src/loom/reconstruction/tsdf_mesh.py`, `gaussian_2dgs.py`)**:
    - Computes TSDF `bounding_center`/`bounding_radius` strictly from high-opacity surfels (`opacity > 0.3`) with 5th–95th percentile trimming, clamped to `<= 1.5 * object_radius`.
    - Sets `voxel_length = bounding_radius / 256.0` and `sdf_trunc = 3.0 * voxel_length`, uses `depth_mode="median"`, and logs View 0 non-zero camera-space Z-depth `min / median / max` before integration.
  - **Diagnostic Convergence Renders (`src/loom/reconstruction/gaussian_2dgs.py`, `scripts/demo.py`)**:
    - Added `compose_debug_panel()` and `Gaussian2DGSReconstructor.save_debug_renders()` exporting `<workspace>/debug_2dgs/{view_0,view_mid,view_last}.png` (`[GT Masked RGB | Rendered 2DGS RGB | 2DGS Median Depth]`).
  - **Tests (`tests/unit/reconstruction/test_gaussian_2dgs.py`, `test_tsdf_mesh.py`)**:
    - Updated tests for `>= 70%` visual-hull filtering, `0.70 -> 0.55` relaxation, `compose_debug_panel`, `opacity > 0.3` + `max_radius` clamping, and `sdf_trunc = 3.0 * voxel_length`.
- **Verification**:
  - `.venv312/bin/pytest tests/ -q`: **267 passed** (0 failures, 0 errors).

---

## Iteration 029 — Fix `gsplat 1.5.3` `rasterization_2dgs` Tensor Shape Crash & Empty-Mask View Guard
- **Date**: 2026-11-22
- **Milestone**: Live RTX 4060 `gsplat 1.5.3` Compatibility & View Filtering Verified (266/266 Tests Passing)
- **Root Cause**:
  - Inspected `gsplat==1.5.3`'s `rasterization_2dgs` source and empirically tested on RTX 4060: `packed=True` is broken upstream in `gsplat 1.5.3` (lines 254–262 broadcast `shs` to `(1, N, K, 3)` without indexing by `[camera_ids, gaussian_ids]`, raising `AssertionError: torch.Size([1, N, 9, 3])`, and lines 234–244 for `sh_degree=None` are commented out).
  - Additionally, `gsplat 1.5.3` returns `surf_normals` with 3D shape `(H, W, 3)` (no leading camera dim), which would have sliced to `(W, 3)` at step 1500.
- **Changes Implemented**:
  - Updated `Gaussian2DGSConfig.packed` default to `False` (`src/loom/reconstruction/gaussian_2dgs.py`, `scripts/demo.py`); for single-camera (`C=1`) steps on $\le 150,000$ surfels, `packed=False` uses ~6 MB and keeps all tensors cleanly aligned.
  - Added ndim-safe unpacking (`ndim == 4` check) for `render_normals`, `surf_normals`, and `render_distort`.
  - Added corrupted/empty mask filtering in `Gaussian2DGSReconstructor.load_training_views()`: excludes views with mask foreground coverage `< 2%` or `> 95%` (with a safety fallback keeping all views if `< 20` valid views remain), protecting both 2DGS training and TSDF fusion.
  - Added unit test `test_load_training_views_excludes_abnormal_masks_with_20_view_fallback` in `tests/unit/reconstruction/test_gaussian_2dgs.py`.
- **Verification**:
  - Live RTX 4060 CUDA smoke test (`gsplat 1.5.3`, `N=100`, `step=1600` normal + distortion + backward + `means2d.grad`): PASSED.
  - `.venv312/bin/pytest tests/ -q`: **266 passed** (0 failures, 0 errors).

---

## Iteration 028 — Fix CPU OOM Kill in `ForegroundMasker` (`src/loom/reconstruction/masking.py`)
- **Date**: 2026-11-22
- **Milestone**: Masked 2DGS Pipeline Memory Hardening (265/265 Tests Passing)
- **Changes Implemented**:
  - Changed default `ForegroundMasker.model_name` from `"birefnet-general"` (973 MB ONNX) to `"isnet-general-use"` while keeping `model_name` configurable (e.g. `"birefnet-general-lite"`).
  - Configured explicit bounded `onnxruntime.SessionOptions()` (`enable_cpu_mem_arena=False`, `enable_mem_pattern=False`, `intra_op_num_threads=4`, `inter_op_num_threads=1`) with `providers=["CPUExecutionProvider"]` in `rembg.new_session(...)`.
  - Added disk-resume skip when output mask PNG already exists in `output_dir`, periodic `gc.collect()` every 10 frames, and explicit `ForegroundMasker.close()` releasing `self._session = None` + `gc.collect()` after `mask_directory()` and in `scripts/demo.py` (`try/finally`).
  - Added unit test `test_foreground_masker_default_model_resume_and_onnx_session_options` in `tests/unit/reconstruction/test_masking.py`.
- **Verification**:
  - `.venv312/bin/pytest tests/ -q`: **265 passed** (0 failures, 0 errors).

---

## Iteration 027 — Masked 2D Gaussian Splatting (2DGS) + BiRefNet + Sparse TSDF Engine (`.venv312`)
- **Date**: 2026-11-22
- **Milestone**: Masked 2DGS + TSDF Reconstruction Engine Complete (264/264 Tests Passing)
- **Changes Implemented**:
  - Created Python 3.12 CUDA environment `.venv312` (`uv`, CPython 3.12.16) with `torch 2.14.1+cu130`, `gsplat 1.5.3`, `rembg`, `open3d 0.20.0`, `trimesh`, `scipy`, `numpy`, `opencv-python`, `mapbox-earcut`, `fastapi`, `uvicorn`, `httpx`, and `pytest`. Added `.venv312/` to `.gitignore`.
  - Created `src/loom/reconstruction/masking.py` (`ForegroundMasker`, `postprocess_alpha_mask`): single-session `birefnet-general` masking on undistorted `dense/images/`, alpha thresholding ($\ge 128$), `3x3` morphological open/close, central primary connected-component retention ($<1\%$ islands pruned), and abnormal coverage warnings ($<2\%$ or $>90\%$).
  - Created `src/loom/reconstruction/gaussian_2dgs.py` (`Gaussian2DGSReconstructor`, `Gaussian2DGSConfig`, `compute_2dgs_loss`, `filter_sparse_points_by_masks`): COLMAP `points3D.bin`/`.txt` parsing, multi-view mask projection filtering ($\ge 2$ views), `gsplat.rasterization_2dgs(render_mode="RGB+ED", distloss=True, packed=True)`, random black/white background compositing, composite photometric + silhouette + post-1500 normal/distortion loss, adaptive densification/pruning capped at `150,000` surfels, `960px`/`720px` VRAM cap, `7000`/`3500` iterations, and structured `[2DGS] Step X/Y` logs.
  - Created `src/loom/reconstruction/tsdf_mesh.py` (`TsdfMeshExtractor`): renders masked median depth + RGB maps (`gt_mask == 0` or `render_alphas < 0.5` zeroed), computes adaptive 2nd–98th percentile foreground sphere ($v = R/256$, $\tau = 4v$), and fuses via Open3D's CPU sparse `o3d.t.geometry.VoxelBlockGrid` (resolving an upstream Open3D `0.20.0` regression where legacy `ScalableTSDFVolume.extract_triangle_mesh()` returned 0 triangles even on canonical `PrimeSenseDefault` depth maps).
  - Integrated `--engine {2dgs,colmap}` (default `2dgs`) into `scripts/demo.py` and added `[MASK]` / `[2DGS]` / `[TSDF]` SSE progress parsing into `src/loom/web/manager.py`.
  - Added fast CPU unit tests: `tests/unit/reconstruction/test_masking.py`, `tests/unit/reconstruction/test_tsdf_mesh.py`, `tests/unit/reconstruction/test_gaussian_2dgs.py`, and SSE 2DGS progress test in `tests/unit/web/test_api.py`.
  - Updated `ARCHITECTURE.md` and `project/CONTEXT.md`.
- **Verification**:
  - `.venv312/bin/pytest tests/ -q`: **264 passed** (0 failures, 0 errors).
  - Verified `scripts/process_bottle.py`, `scripts/lock_master_stl.py`, `data/`, and `outputs/stl/` remained untouched.

---

## Iteration 026 — Phase 2 Track A: FastAPI Local GPU Worker & Live Vercel Bridge (`src/loom/web/`)
- **Date**: 2026-11-22
- **Milestone**: Phase 2 Track A Complete (Local RTX 4060 GPU Worker + SSE Bridge)
- **Changes Implemented**:
  - Installed `fastapi==0.165.0`, `uvicorn[standard]==0.54.0`, `python-multipart==0.0.34`, and `httpx==0.28.1` into existing `.venv`.
  - Created `src/loom/web/models.py`: typed Pydantic v2 models (`JobStatus`, `HealthResponse`, `JobCreateResponse`, `JobSummary`).
  - Created `src/loom/web/manager.py`: `ReconstructionJobManager` implementing:
    - 1 MB streaming disk ingest to `outputs/web_jobs/<job_id>/input<ext>` with extension (`{.mp4, .webm, .mov}`) and 500 MB size validation.
    - Optional `ffmpeg` `.webm` remux/transcode (`libx264 -preset fast -crf 18 -an`) with graceful fallback when `ffmpeg` is absent.
    - Strict single-GPU 1-job-at-a-time FIFO worker via `asyncio.Queue` spawning `scripts/demo.py` with `--stl-dir <job_dir>/stl` and `_build_subprocess_env()` CUDA linker inheritance.
    - Bounded 2000-line log ring buffer, monotonic 8-stage progress inference, live SSE fan-out (`event: log`, `event: progress`, 15s heartbeats, `event: done`), and clean subprocess cancellation (`terminate()` -> 5s -> `kill()`).
  - Created `src/loom/web/app.py`: FastAPI application with Vercel CORS (`https://loomvidcapture.vercel.app`, `localhost:5173`, `https://.*\.vercel\.app`) and all 8 endpoints (`/health`, `/api/reconstruct`, `/api/jobs`, `/api/jobs/{job_id}`, `/api/jobs/{job_id}/stream`, `/api/jobs/{job_id}/stl`, `/api/jobs/{job_id}/manifest`, `DELETE /api/jobs/{job_id}`).
  - Created executable launcher `scripts/serve_worker.py` (`--host`, `--port`, Cloudflare HTTPS tunnel command instructions).
  - Added unit test suite `tests/unit/web/test_api.py` covering `/health` + CORS, upload validation (`400`/`413`/`202`), strict FIFO serialization, SSE live streaming, binary STL + manifest downloads, active cancellation, `.webm` fallback, and error log capture.
  - Updated `ARCHITECTURE.md` and `project/CONTEXT.md`.
- **Verification**:
  - `.venv/bin/pytest tests/ -q`: **253 passed** (248 existing + 5 web API tests; web tests run in < 1s without calling real COLMAP).
  - Verified `scripts/process_bottle.py`, `scripts/lock_master_stl.py`, `data/`, and `outputs/stl/` remained untouched.

---

## Iteration 025 — Phase 1 Core Stabilization, Geometric Defect Resolution & Repo Hygiene
- **Date**: 2026-11-21
- **Milestone**: Phase 1 Core Stabilization Complete (248/248 Tests Passing)
- **Changes Implemented**:
  - **Fixed Blocking Syntax Error (`src/loom/mesh/processor.py`)**:
    - Removed duplicate empty `if cull_action is None:` on line 157 preceding `if cull_action is None and not active_cfg.turbo:`.
    - Added missing `Any` import to typing declarations.
  - **Hardened Canonical Alignment (`src/loom/geometry/alignment.py`, `tests/unit/geometry/test_alignment.py`)**:
    - Confirmed full-cloud vectorized RANSAC (`max_iterations=1500`, zero camera-Z 35% clipping), camera-centroid upward gravity polarity ($\mathbf{n} \cdot (\mathbf{C}_{\text{cam}} - \mathbf{p}_0) > 0$), and synchronous Rodrigues $SO(3)$ rotation of vertices and re-normalized unit normals `(nx, ny, nz)`.
    - Added unit tests for steeply tilted planes, synchronous normal rotation + PLY round-trip, and negative-hemisphere camera polarity inversion.
  - **Verified Watertight Poisson & SfM Circuit Breaker (`src/loom/reconstruction/colmap.py`)**:
    - Confirmed `--PoissonMeshing.trim 0` across `build_poisson_mesher_args`, `run_poisson_mesher`, and `reconstruct_dense`, and verified the $<75\%$ registered-view SfM circuit breaker in `reconstruct()`.
  - **Fixed CUDA Dynamic Linker Path (`src/loom/utils/subprocess.py`, `tests/unit/test_utils.py`)**:
    - Added `_build_subprocess_env()` automatically prepending `/opt/cuda/lib64` to `LD_LIBRARY_PATH` when present on host for both streaming (`Popen`) and buffered (`run`) subprocess calls.
    - Added unit tests covering CUDA linker path injection and deduplication.
  - **Generalized Target-Length Fallback Scaling (`scripts/demo.py`)**:
    - Removed hardcoded shoe fallback paths (`shoe_2.mp4` / `shoe_1.mp4`) and shoe-specific `280.0` CLI help default; set `--target-length` default to `200.0` mm applied uniformly in `float64` memory with build-plate snap $Z_{\min} = 0.000000\text{ mm}$.
    - Added missing `import numpy as np` and hardened `Path` guard before `trimesh.load`.
  - **Repository Hygiene (`.gitignore` & Root Cleanup)**:
    - Removed stray untracked Vite/React frontend files (`index.html`, `package.json`, `package-lock.json`, `tsconfig*.json`, `vercel.json`, `vite.config.ts`, `node_modules/`).
    - Added `*.db` and `*.bin` to `.gitignore`.
  - **Documentation Synchronization**:
    - Updated `AGENTS.md` (Linux `/home/synapse/Documents/LOOM` paths, COLMAP 4.2.0 CUDA & `.venv` rules).
    - Created root `ARCHITECTURE.md` documenting the 8-stage pipeline, module boundaries, and invariants.
    - Rewrote `README.md` with accurate Linux/CUDA setup, CLI commands, and verified 248-test count.
    - Updated `project/CONTEXT.md`.
- **Verification**:
  - `.venv/bin/pytest tests/ -q`: **248 passed in 4.84s** (0 failures, 0 errors).
  - `run_subprocess(['colmap', '-h'], stream_output=False)`: exited `0` (`COLMAP 4.2.0 (Commit be5e29168 on 2026-08-31 with CUDA)`).
  - Verified `scripts/process_bottle.py`, `outputs/`, and `data/` remained completely untouched.

---

## Iteration 024 — Robust Production Photogrammetry Engine (< 220s, Any Object)
- **Date**: 2026-11-12
- **Milestone**: Phases 1–8 Production Ready & Verified End-to-End
- **Context & Motivation**:
  - Unconstrained smartphone scans previously suffered from three failure modes:
    1. Tracking drops during 360-degree orbit if sequential matching overlap was throttled too low.
    2. Upward gravity inversion if the support plane normal pointed away from the camera hemisphere.
    3. Starburst triangle fan artifacts bridging empty voids if holes exceeded conservative thresholds.
  - Objective: Implement robust video ingest (68 frames @ 960px, Laplacian threshold 18.0), full sequential matching (overlap 10, quadratic overlap 1, loop detection 1), SfM Circuit Breaker (<75% registration abort), dense MVS (960px, window radius 4, 3 iters, min_num_pixels 3), camera centroid upward polarity check, anti-starburst boundary loop guard (>60 edges rejected), and automated flush build plate snapping.
- **Changes Implemented**:
  - Video Ingest & Downscaling (`src/loom/video/frames.py`):
    - Configured turbo default frame target to 68 keyframes.
    - Downscaled extracted keyframes to max dimension 960 using `cv2.INTER_AREA`.
    - Set blur rejection threshold to $\tau = 18.0$ Laplacian variance.
  - High-Speed Robust COLMAP Engine (`src/loom/reconstruction/colmap.py`):
    - Sequential matching: enforced `--SequentialMatching.overlap 10`, `--SequentialMatching.quadratic_overlap 1`, `--SequentialMatching.loop_detection 1`, and `--FeatureMatching.use_gpu 1`.
    - Mapper: 16 threads, `ba_global=15`, `ba_local=12`, `min_num_matches=15`.
    - **SfM Circuit Breaker**: Evaluates `images.bin` / `images.txt`. If registered camera count is $< 75\%$ of input frames, aborts with `RuntimeError("SfM tracking lost: insufficient overlap or texture. Aborting to prevent invalid geometry.")`.
    - Dense MVS: PatchMatch stereo max size 960, window radius 4, 3 iterations, geometric consistency false in turbo mode.
    - Stereo Fusion: `--StereoFusion.min_num_pixels 3`.
  - Support Plane Alignment & Pre-Mesh Culling (`src/loom/geometry/alignment.py`, `segmentation.py`):
    - Vectorized RANSAC support plane fitting with 1500 iterations.
    - **Upward Gravity Polarity Check**: Computes camera trajectory centroid $\mathbf{C}_{\text{cam}}$ and plane anchor point $\mathbf{p}_0 = -d \cdot \mathbf{n}$. If $\mathbf{n} \cdot (\mathbf{C}_{\text{cam}} - \mathbf{p}_0) < 0 \implies \mathbf{n} = -\mathbf{n}, d = -d$.
    - Rodrigues $SO(3)$ rotation aligning support plane normal to $[0, 0, 1]^T$ applied synchronously to points and normal vectors.
    - Canonical translation placing support plane at $Z = 0.0$ and median of elevated points ($Z > 0.015$) at $(0.0, 0.0)$.
    - Foreground segmentation: sub-plane cutoff at $Z = -0.005$ and cylindrical crop at $R_{\text{cut}} = 1.30 \times \text{percentile}(R_{xy}, 98)$.
  - Surface Reconstruction & Anti-Starburst Capping (`src/loom/mesh/repair.py`):
    - Poisson meshing at depth 10, trim 0, point_weight 1.0 on `dense/fused_isolated.ply`.
    - Planar base cut at $Z = 0.005$ sealed flat with `mapbox-earcut` ($\mathbf{n} = [0, 0, -1]^T$).
    - **Anti-Starburst Guard**: Rejects hole-filling for any boundary loop containing $> 60$ edges.
    - Enforced positive volume inversion (`if mesh.volume < 0: mesh.faces = mesh.faces[:, ::-1]`).
  - Metric Scaling & Validated STL Export (`scripts/demo.py`):
    - Default `--target-length` 200.0 mm in turbo mode.
    - Base flush snap to $Z_{\min} = 0.000000$ mm.
    - Manufacturing readiness check via `PrintabilityGate` and validated binary STL export with JSON manifest.
- **Verification**:
  - Full test suite: 245 passed in 4.35s (`pytest tests/`).
  - Added unit test `test_reconstruct_sfm_circuit_breaker` verifying $<75\%$ view registration abort.
  - Executed end-to-end demo: `PrintabilityGate` PASSED (`watertight=True`, `boundary_edge_count=0`, `non_manifold_edge_count=0`, `non_manifold_vertex_count=0`, positive volume $4,287,238.8\,\text{mm}^3$).
  - Binary STL exported: `outputs/stl/cleaned_meshed-poisson_metric.stl` (91,600 triangles) with valid timing manifest JSON.

---

## Iteration 023 — Universal Video-to-Print Overhaul (Pre-Mesh Canonical Normalization, Depth 10 Poisson, Validated Binary STL)
- **Date**: 2026-11-10
- **Milestone**: Phases 1–8 Fully Operational & Verified on Tabletop Videos
- **Context & Motivation**:
  - Unconstrained Poisson meshing at depth 9 previously blurred details into potato blobs, while meshing raw clouds containing floor/walls caused mesh bridging and ballooning into unobserved air.
  - Slicing unaligned meshes caused 30-degree diagonal cuts through the subject.
  - Overhaul requirement: Pre-mesh support plane canonical normalization, normal vector rotation (`property float nx, ny, nz`), cylindrical foreground isolation before meshing, native COLMAP depth 10 Poisson meshing, planar bed slicing at $Z=0.005$, and verified watertight binary STL export.
- **Changes Implemented**:
  - Vectorized Normal I/O & Transformation (`src/loom/geometry/alignment.py`):
    - Added `read_ply_with_normals(path)` and `write_ply_with_normals(path, vertices, normals, colors)` supporting binary little-endian PLY files with standard float32 `x, y, z, nx, ny, nz` properties and uint8 colors.
    - Updated `CoordinateNormalizer.fit_support_plane_ransac()`: sample up to 60,000 points, threshold $0.012 \times \text{bbox\_diagonal}$, polarity check against median signed distance of non-inliers.
    - Updated `CoordinateNormalizer.compute_alignment_matrix()`: Rodrigues rotation to $[0, 0, 1]^T$, translation to $Z=0.0$, and XY centering of elevated points ($Z > 0.02$).
    - Transformed vertex normal vectors in lockstep: $\mathbf{n}' = \mathbf{n} R^T$.
  - Foreground Segmentation with Normal Preservation (`src/loom/geometry/segmentation.py`):
    - Discarded subsurface noise points ($Z < -0.005$).
    - Computed 98th percentile radius $R_{98}$ on elevated points ($Z > 0.02$) and performed cylindrical crop at $R_{\text{cut}} = 1.25 \times R_{98}$.
    - Exported isolated, leveled point cloud directly to `dense/fused_isolated.ply` with rotated normals.
  - Native Depth 10 Poisson Meshing (`src/loom/reconstruction/colmap.py`):
    - In `ColmapAdapter.reconstruct_dense()`, passed `dense/fused_isolated.ply` directly to `colmap poisson_mesher` with `--PoissonMeshing.depth 10`, `--PoissonMeshing.point_weight 1.0`, `--PoissonMeshing.trim 0`.
    - Eliminated mesh ballooning and eliminated Delaunay mesher fallback.
  - Turbo Reconstruction Acceleration (`src/loom/reconstruction/colmap.py`):
    - Sequential matching: `overlap=6`, `quadratic_overlap=0`, `loop_detection=1`, `use_gpu=1`.
    - Mapper: 16 threads, `ba_global_max_num_iterations=15`, `ba_local_max_num_iterations=12`.
    - PatchMatch stereo: `gpu_index=0`, `max_image_size=1080`, `window_radius=5`, `num_iterations=4`, `geom_consistency=True`, `geom_consistency_max_cost=2.5`.
    - Stereo fusion: `min_num_pixels=3`.
  - Guaranteed Planar Bed Adhesion (`src/loom/mesh/repair.py`):
    - Sliced bottom perimeter at $Z = 0.0051$ with horizontal cut plane normal $[0, 0, 1]^T$.
    - Sealed bottom opening flat with 12,257 `mapbox-earcut` triangles ($\mathbf{n} = [0, 0, -1]^T$).
    - Sealed remaining top apertures with `trimesh.repair.fill_holes()` and enforced positive volume.
  - CLI Integration & In-Memory Scaling (`scripts/demo.py`):
    - Scaled mesh uniformly to `--target-length 280.0` in float64 memory ($s = 78.87543$).
    - Snapped flat sole flush to $Z = 0.0$ (`mesh.vertices[:, 2] -= mesh.bounds[0][2]`).
    - Centered model on $(X=0, Y=0)$.
    - Validated with `PrintabilityGate` and exported binary STL with JSON manifest.
    - Added stage timing breakdown output.
- **Empirical Verification (`outputs/live_demo_test`)**:
  - Input: `data/raw/shoe_3.mp4` (229 MB, 3269 raw frames).
  - Command: `.venv/bin/python scripts/demo.py --video data/raw/shoe_3.mp4 --output-dir outputs/live_demo_test --turbo --target-length 280.0 --export-stl`
  - Total Turnaround Time: **283.93s** (Ingest: 37.04s, SfM: 4.21s, Dense MVS & Meshing: 220.67s, Cleaning & Capping: 15.55s, Scaling & STL Export: 5.50s).
  - Poisson Mesher: Succeeded with 312,897 vertices and 625,602 faces.
  - Planar Base Capping: 12,257 cap faces added across 136 boundary loops.
  - Printability Gate Validation: **PASSED** (watertight=True, boundary_edge_count=0, non_manifold_edge_count=0, non_manifold_vertex_count=0, volume=$67,206.02\,\text{mm}^3$).
  - Target Dimensions: $L = 280.0\,\text{mm}$, $W = 224.4\,\text{mm}$, $H = 89.8\,\text{mm}$.
  - Bed Contact: $Z_{\min} = 0.000000\,\text{mm}$ (perfectly flush).
  - Output Artifacts:
    - STL: `outputs/stl/cleaned_meshed-poisson_metric.stl` (539,590 triangles, 26,979,584 bytes).
    - Manifest: `outputs/stl/cleaned_meshed-poisson_metric_manifest.json` (SHA256: `a66f79a2d1da64d1d11b88eecbd869d15fb0b8e17d07bc1cc855d0c3df574e1c`).
  - Unit/Integration Tests: 243 passed in 4.25s.

---

## Iteration 022 — Unified Turbo Video-to-3D-Print Pipeline (< 200s Total Runtime Benchmark)
- **Date**: 2026-11-10
- **Milestone**: Phase 1 / Phase 2 / Phase 3 / Phase 4 / Phase 7 / Phase 8 — End-to-End Turbo Pipeline Benchmark Verified
- **Context & Motivation**:
  - Processing hundreds of unconstrained video frames through unoptimized photogrammetry caused 25+ minute bottlenecks, thermal throttling, and memory crashes.
  - Requirement: End-to-end turnaround under 200s (3.5 minutes) from raw smartphone video to a 100% watertight, validated, 2-manifold binary STL.
- **Changes Implemented**:
  - Video Ingest & Downscaling (`src/loom/video/frames.py`, `src/loom/config/models.py`):
    - Added `target_max_dimension: Optional[int] = 960` and `turbo: bool = False` to `VideoConfig`.
    - Downscaled extracted keyframes using `cv2.INTER_AREA` when $\max(H, W) > 960$.
    - In `--turbo` mode, defaulted `max_frames = 36` with even duration striding and Laplacian blur filtering.
  - Live Subprocess Streaming (`src/loom/utils/subprocess.py`):
    - Re-architected `run_subprocess()` with `stream_output=True` using `subprocess.Popen` and daemon pipe reader threads to stream live progress to stdout/stderr while capturing full output.
  - Reconstruction Acceleration (`src/loom/reconstruction/colmap.py`):
    - Added `turbo` flag to `ColmapAdapter.run_matching()`, `run_mapper()`, `run_stereo_fusion()`, and `reconstruct_dense()`.
    - Matching: GPU sequential matching with `overlap=5`, `quadratic_overlap=0`.
    - Mapper: 16 threads, bounded bundle adjustment iterations (`ba_global=12`, `ba_local=10`).
    - Dense MVS: Single-pass photometric stereo (`window_radius=4`, `num_iterations=3`, `geom_consistency=False`, `max_image_size=960`).
    - Meshing: Poisson mesher at depth 9 with `trim=0` directly on `fused.ply` containing native normal vectors.
  - Planar Base Capping with `mapbox-earcut` (`src/loom/mesh/repair.py`):
    - Replaced centroid fan triangulation on base cut loops with `mapbox_earcut.triangulate_float64` (with fallback to pure ear clipping), eliminating self-intersections on non-convex soles.
    - Verified outward downward normal orientation ($n_z < 0$) for all base cap triangles.
  - CLI Turbo Pipeline Integration (`scripts/demo.py`):
    - Added `--turbo` flag auto-configuring `max_frames=36`, `max_image_size=960`, `dense=True`, `align_support=True`, `clean_mesh=True`, `remove_floor=True`, `cap_base=True`, and `base_z=0.005`.
    - Added graceful video path resolution falling back to repository candidates (`data/raw/shoe_2.mp4`).
  - Unit Tests:
    - Added `test_colmap_adapter_turbo_flags` and `test_demo_turbo_cli` in `tests/unit/reconstruction/test_colmap_adapter.py`.
    - Total test suite: 240 passed in 4.55s.
- **Empirical Verification (`outputs/turbo_run`)**:
  - Command: `.venv/bin/python scripts/demo.py --video data/raw/shoe_2.mp4 --output-dir outputs/turbo_run --turbo --target-length 280.0 --export-stl`
  - Total end-to-end turnaround: **151.0 seconds** (2.5 minutes, beating < 200s target).
  - Frame extraction: 36 frames downscaled to $540 \times 960$ in 51.8s.
  - Sparse SfM: SIFT GPU extraction + sequential matching + 16-thread mapper in 7.0s.
  - Dense MVS & Meshing: 88.69s (photometric stereo in 25s, fusion 183k points, Poisson mesher 65,666 verts in 1.6s).
  - Canonical Alignment: RANSAC support plane normal $[0.163, -0.541, -0.825]$ rotated to $[0, 0, 1]^T$ at $Z=0$.
  - Phase 3 Cleaning & Planar Slicing: 5,415 `mapbox-earcut` cap faces across 65 loops at $Z=0.005$.
  - Target Scaling: Uniform scaling ($s=22.78428$) to 280.0 mm in float64 memory.
  - Printability Gate: **PASSED** (watertight=True, 0 boundary edges, 0 non-manifold edges, 0 non-manifold vertices, volume=$448,368.5\,\text{mm}^3$).
  - Binary STL Exported: `outputs/stl/cleaned_aligned_meshed-poisson_metric.stl` (86,850 faces, 4,342,584 bytes).
  - JSON Manifest: `outputs/stl/cleaned_aligned_meshed-poisson_metric_manifest.json`.

---

## Iteration 022 — Unified Turbo Video-to-3D-Print Pipeline (< 200s Total Runtime Benchmark)
- **Date**: 2026-11-10
- **Milestone**: Phase 1 / Phase 2 / Phase 3 / Phase 4 / Phase 7 / Phase 8 — End-to-End Turbo Pipeline Benchmark Verified
- **Context & Motivation**:
  - Processing hundreds of unconstrained video frames through unoptimized photogrammetry caused 25+ minute bottlenecks, thermal throttling, and memory crashes.
  - Requirement: End-to-end turnaround under 200s (3.5 minutes) from raw smartphone video to a 100% watertight, validated, 2-manifold binary STL.
- **Changes Implemented**:
  - Video Ingest & Downscaling (`src/loom/video/frames.py`, `src/loom/config/models.py`):
    - Added `target_max_dimension: Optional[int] = 960` and `turbo: bool = False` to `VideoConfig`.
    - Downscaled extracted keyframes using `cv2.INTER_AREA` when $\max(H, W) > 960$.
    - In `--turbo` mode, defaulted `max_frames = 36` with even duration striding and Laplacian blur filtering.
  - Live Subprocess Streaming (`src/loom/utils/subprocess.py`):
    - Re-architected `run_subprocess()` with `stream_output=True` using `subprocess.Popen` and daemon pipe reader threads to stream live progress to stdout/stderr while capturing full output.
  - Reconstruction Acceleration (`src/loom/reconstruction/colmap.py`):
    - Added `turbo` flag to `ColmapAdapter.run_matching()`, `run_mapper()`, `run_stereo_fusion()`, and `reconstruct_dense()`.
    - Matching: GPU sequential matching with `overlap=5`, `quadratic_overlap=0`.
    - Mapper: 16 threads, bounded bundle adjustment iterations (`ba_global=12`, `ba_local=10`).
    - Dense MVS: Single-pass photometric stereo (`window_radius=4`, `num_iterations=3`, `geom_consistency=False`, `max_image_size=960`).
    - Meshing: Poisson mesher at depth 9 with `trim=0` directly on `fused.ply` containing native normal vectors.
  - Planar Base Capping with `mapbox-earcut` (`src/loom/mesh/repair.py`):
    - Replaced centroid fan triangulation on base cut loops with `mapbox_earcut.triangulate_float64` (with fallback to pure ear clipping), eliminating self-intersections on non-convex soles.
    - Verified outward downward normal orientation ($n_z < 0$) for all base cap triangles.
  - CLI Turbo Pipeline Integration (`scripts/demo.py`):
    - Added `--turbo` flag auto-configuring `max_frames=36`, `max_image_size=960`, `dense=True`, `align_support=True`, `clean_mesh=True`, `remove_floor=True`, `cap_base=True`, and `base_z=0.005`.
    - Added graceful video path resolution falling back to repository candidates (`data/raw/shoe_2.mp4`).
  - Unit Tests:
    - Added `test_colmap_adapter_turbo_flags` and `test_demo_turbo_cli` in `tests/unit/reconstruction/test_colmap_adapter.py`.
    - Total test suite: 240 passed in 4.55s.
- **Empirical Verification (`outputs/turbo_run`)**:
  - Command: `.venv/bin/python scripts/demo.py --video data/raw/shoe_2.mp4 --output-dir outputs/turbo_run --turbo --target-length 280.0 --export-stl`
  - Total end-to-end turnaround: **151.0 seconds** (2.5 minutes, beating < 200s target).
  - Frame extraction: 36 frames downscaled to $540 \times 960$ in 51.8s.
  - Sparse SfM: SIFT GPU extraction + sequential matching + 16-thread mapper in 7.0s.
  - Dense MVS & Meshing: 88.69s (photometric stereo in 25s, fusion 183k points, Poisson mesher 65,666 verts in 1.6s).
  - Canonical Alignment: RANSAC support plane normal $[0.163, -0.541, -0.825]$ rotated to $[0, 0, 1]^T$ at $Z=0$.
  - Phase 3 Cleaning & Planar Slicing: 5,415 `mapbox-earcut` cap faces across 65 loops at $Z=0.005$.
  - Target Scaling: Uniform scaling ($s=22.78428$) to 280.0 mm in float64 memory.
  - Printability Gate: **PASSED** (watertight=True, 0 boundary edges, 0 non-manifold edges, 0 non-manifold vertices, volume=$448,368.5\,\text{mm}^3$).
  - Binary STL Exported: `outputs/stl/cleaned_aligned_meshed-poisson_metric.stl` (86,850 faces, 4,342,584 bytes).
  - JSON Manifest: `outputs/stl/cleaned_aligned_meshed-poisson_metric_manifest.json`.

---

## Iteration 021 — Canonical Pre-Cleaning Handoff, Floater Pruning & Printability Gate End-to-End Verification
- **Date**: 2026-11-10
- **Milestone**: Phase 3 / Phase 4 / Phase 7 / Phase 8 — Watertight Base-Capped Canonical STL Verification
- **Changes Implemented**:
  - Sequential Handoff Inversion (`scripts/demo.py`):
    - Reordered pipeline operations so `--align-support` canonical normalization executes BEFORE Phase 3 mesh cleaning (`clean_mesh`).
    - Aligns both the raw mesh and the dense point cloud (`fused.ply`) via the identical $4 \times 4$ homogeneous transformation matrix $T$, ensuring KDTree point cloud distance culling operates in the exact same aligned space.
    - Added `--base-z <float>` CLI argument to `scripts/demo.py` (defaults to $Z=0.005$ when `--align-support` is active) so base slicing cuts parallel to the canonical floor plane rather than diagonally across the subject.
    - Eliminated redundant `merge_vertices()` call during in-memory target-length scaling, preventing edge snapping that previously reintroduced 12 non-manifold edges on already watertight meshes.
  - Floater Pruning on Slicing Boundary (`src/loom/mesh/repair.py`):
    - In `MeshRepairer.slice_and_cap_base`: added post-capping connected component pruning using `MeshComponentAnalyzer.get_face_components()`. When a dominant primary body exists (> 1,000 faces), tiny disconnected 1-to-10 triangle floaters generated along the planar cut boundary (< 5% of primary component) are safely pruned.
    - Pruned 92 floating slivers around the cut perimeter, restoring complete 100% watertightness with 0 open boundary edges and positive volume.
  - End-to-End Pipeline Execution on Dense Shoe Model:
    - Executed: `scripts/demo.py --mesh-only outputs/demo/dense/meshed-poisson.ply --point-cloud outputs/demo/dense/fused.ply --align-support --clean-mesh --cap-base --base-z 0.005 --target-length 280.0 --export-stl`.
    - Recovered 100% watertight, 2-manifold STL:
      - Raw mesh: 543,013 vertices, 1,084,399 faces.
      - Aligned support plane normal: $[-0.093, -0.464, 0.881]$ (rotated 28.2° to $[0, 0, 1]$, $Z=0$).
      - KDTree distance culling: 440,699 balloon faces removed -> 643,700 faces.
      - Component isolation: selected Component #0 (327,276 faces).
      - Planar base capping ($Z=0.005$): added 12,026 cap faces across 243 loops -> 254,618 faces.
      - Floater pruning & defect repair: 0 remaining boundary edges, 0 boundary loops.
      - Target scaling ($s=161.40689$): maximum dimension 280.0 mm.
      - Printability Gate: PASSED (watertight=True, manifold=True, positive_volume=True).
      - STL Export: `outputs/stl/cleaned_aligned_meshed-poisson_metric.stl` (12.7 MB, 254,618 triangles).
      - OBB: $299.7 \times 253.6 \times 75.0\,\text{mm}$, Volume: $794,059.0\,\text{mm}^3$.
  - Unit Tests:
    - Added `test_demo_base_z_cli` in `tests/unit/reconstruction/test_colmap_adapter.py`.
    - Total test suite: 235 passed in 4.39s.

---

## Iteration 022 — Unified Turbo Video-to-3D-Print Pipeline (< 200s Total Runtime Benchmark)
- **Date**: 2026-11-10
- **Milestone**: Phase 1 / Phase 2 / Phase 3 / Phase 4 / Phase 7 / Phase 8 — End-to-End Turbo Pipeline Benchmark Verified
- **Context & Motivation**:
  - Processing hundreds of unconstrained video frames through unoptimized photogrammetry caused 25+ minute bottlenecks, thermal throttling, and memory crashes.
  - Requirement: End-to-end turnaround under 200s (3.5 minutes) from raw smartphone video to a 100% watertight, validated, 2-manifold binary STL.
- **Changes Implemented**:
  - Video Ingest & Downscaling (`src/loom/video/frames.py`, `src/loom/config/models.py`):
    - Added `target_max_dimension: Optional[int] = 960` and `turbo: bool = False` to `VideoConfig`.
    - Downscaled extracted keyframes using `cv2.INTER_AREA` when $\max(H, W) > 960$.
    - In `--turbo` mode, defaulted `max_frames = 36` with even duration striding and Laplacian blur filtering.
  - Live Subprocess Streaming (`src/loom/utils/subprocess.py`):
    - Re-architected `run_subprocess()` with `stream_output=True` using `subprocess.Popen` and daemon pipe reader threads to stream live progress to stdout/stderr while capturing full output.
  - Reconstruction Acceleration (`src/loom/reconstruction/colmap.py`):
    - Added `turbo` flag to `ColmapAdapter.run_matching()`, `run_mapper()`, `run_stereo_fusion()`, and `reconstruct_dense()`.
    - Matching: GPU sequential matching with `overlap=5`, `quadratic_overlap=0`.
    - Mapper: 16 threads, bounded bundle adjustment iterations (`ba_global=12`, `ba_local=10`).
    - Dense MVS: Single-pass photometric stereo (`window_radius=4`, `num_iterations=3`, `geom_consistency=False`, `max_image_size=960`).
    - Meshing: Poisson mesher at depth 9 with `trim=0` directly on `fused.ply` containing native normal vectors.
  - Planar Base Capping with `mapbox-earcut` (`src/loom/mesh/repair.py`):
    - Replaced centroid fan triangulation on base cut loops with `mapbox_earcut.triangulate_float64` (with fallback to pure ear clipping), eliminating self-intersections on non-convex soles.
    - Verified outward downward normal orientation ($n_z < 0$) for all base cap triangles.
  - CLI Turbo Pipeline Integration (`scripts/demo.py`):
    - Added `--turbo` flag auto-configuring `max_frames=36`, `max_image_size=960`, `dense=True`, `align_support=True`, `clean_mesh=True`, `remove_floor=True`, `cap_base=True`, and `base_z=0.005`.
    - Added graceful video path resolution falling back to repository candidates (`data/raw/shoe_2.mp4`).
  - Unit Tests:
    - Added `test_colmap_adapter_turbo_flags` and `test_demo_turbo_cli` in `tests/unit/reconstruction/test_colmap_adapter.py`.
    - Total test suite: 240 passed in 4.55s.
- **Empirical Verification (`outputs/turbo_run`)**:
  - Command: `.venv/bin/python scripts/demo.py --video data/raw/shoe_2.mp4 --output-dir outputs/turbo_run --turbo --target-length 280.0 --export-stl`
  - Total end-to-end turnaround: **151.0 seconds** (2.5 minutes, beating < 200s target).
  - Frame extraction: 36 frames downscaled to $540 \times 960$ in 51.8s.
  - Sparse SfM: SIFT GPU extraction + sequential matching + 16-thread mapper in 7.0s.
  - Dense MVS & Meshing: 88.69s (photometric stereo in 25s, fusion 183k points, Poisson mesher 65,666 verts in 1.6s).
  - Canonical Alignment: RANSAC support plane normal $[0.163, -0.541, -0.825]$ rotated to $[0, 0, 1]^T$ at $Z=0$.
  - Phase 3 Cleaning & Planar Slicing: 5,415 `mapbox-earcut` cap faces across 65 loops at $Z=0.005$.
  - Target Scaling: Uniform scaling ($s=22.78428$) to 280.0 mm in float64 memory.
  - Printability Gate: **PASSED** (watertight=True, 0 boundary edges, 0 non-manifold edges, 0 non-manifold vertices, volume=$448,368.5\,\text{mm}^3$).
  - Binary STL Exported: `outputs/stl/cleaned_aligned_meshed-poisson_metric.stl` (86,850 faces, 4,342,584 bytes).
  - JSON Manifest: `outputs/stl/cleaned_aligned_meshed-poisson_metric_manifest.json`.

---



---

## Iteration 020 — Canonical Frame Normalization via RANSAC Support Plane Alignment
- **Date**: 2026-11-10
- **Milestone**: Phase 4 — Canonical Coordinate Frame Normalization & Pipeline Integration
- **Changes Implemented**:
  - Module Creation (`src/loom/geometry/alignment.py`):
    - Implemented `PlaneModel` dataclass representing support plane parametric form ($n \cdot x + d = 0$).
    - Implemented `AlignmentResult` dataclass packaging rotation matrix $\mathbf{R}$, translation vector $\mathbf{t}$, homogeneous transform $\mathbf{T}_{4 \times 4}$, plane model, and normalized point array.
    - Implemented `CoordinateNormalizer`:
      - `fit_support_plane_ransac()`: Vectorized RANSAC dominant plane estimator with polarity check directing the normal upward toward the non-plane object mass.
      - `compute_alignment_matrix()`: $SO(3)$ Rodrigues rotation mapping support normal to target $[0, 0, 1]^T$, translating the support plane to $Z = 0$, and centering the subject at $(X = 0, Y = 0)$.
      - `normalize()`: Multi-type normalizer accepting `np.ndarray`, `trimesh.PointCloud`, and `trimesh.Trimesh`.
  - Package Export Integration:
    - Exported `PlaneModel`, `AlignmentResult`, and `CoordinateNormalizer` from `src/loom/geometry/__init__.py`.
  - Pipeline & Script Integration:
    - Integrated `CoordinateNormalizer` into `scripts/align_and_isolate.py`.
    - Added `--align-support` argument in `scripts/demo.py` to enable canonical coordinate normalization on reconstructed meshes.
  - Comprehensive Test Suite:
    - Added `tests/unit/geometry/test_alignment.py` covering synthetic tilted scene recovery, insufficient point guards, raw array normalization, `trimesh.Trimesh` transform preservation, and `trimesh.PointCloud` color preservation.
    - Added `test_demo_align_support_cli` in `tests/unit/reconstruction/test_colmap_adapter.py`.
- **Verification**:
  - Full test suite: 234 passed in 4.38s.
  - Geometry unit tests: 9 passed in 0.48s.
  - Aligned 467k-point dense shoe cloud `outputs/demo/dense/fused.ply`: detected floor plane with normal $[0.214, 0.122, -0.969]$ (71,994 inliers), aligned support to $Z = 0$, centered XY at $(0, 0)$, and isolated shoe foreground (186,659 points) in 3.0s.

---

## Iteration 022 — Unified Turbo Video-to-3D-Print Pipeline (< 200s Total Runtime Benchmark)
- **Date**: 2026-11-10
- **Milestone**: Phase 1 / Phase 2 / Phase 3 / Phase 4 / Phase 7 / Phase 8 — End-to-End Turbo Pipeline Benchmark Verified
- **Context & Motivation**:
  - Processing hundreds of unconstrained video frames through unoptimized photogrammetry caused 25+ minute bottlenecks, thermal throttling, and memory crashes.
  - Requirement: End-to-end turnaround under 200s (3.5 minutes) from raw smartphone video to a 100% watertight, validated, 2-manifold binary STL.
- **Changes Implemented**:
  - Video Ingest & Downscaling (`src/loom/video/frames.py`, `src/loom/config/models.py`):
    - Added `target_max_dimension: Optional[int] = 960` and `turbo: bool = False` to `VideoConfig`.
    - Downscaled extracted keyframes using `cv2.INTER_AREA` when $\max(H, W) > 960$.
    - In `--turbo` mode, defaulted `max_frames = 36` with even duration striding and Laplacian blur filtering.
  - Live Subprocess Streaming (`src/loom/utils/subprocess.py`):
    - Re-architected `run_subprocess()` with `stream_output=True` using `subprocess.Popen` and daemon pipe reader threads to stream live progress to stdout/stderr while capturing full output.
  - Reconstruction Acceleration (`src/loom/reconstruction/colmap.py`):
    - Added `turbo` flag to `ColmapAdapter.run_matching()`, `run_mapper()`, `run_stereo_fusion()`, and `reconstruct_dense()`.
    - Matching: GPU sequential matching with `overlap=5`, `quadratic_overlap=0`.
    - Mapper: 16 threads, bounded bundle adjustment iterations (`ba_global=12`, `ba_local=10`).
    - Dense MVS: Single-pass photometric stereo (`window_radius=4`, `num_iterations=3`, `geom_consistency=False`, `max_image_size=960`).
    - Meshing: Poisson mesher at depth 9 with `trim=0` directly on `fused.ply` containing native normal vectors.
  - Planar Base Capping with `mapbox-earcut` (`src/loom/mesh/repair.py`):
    - Replaced centroid fan triangulation on base cut loops with `mapbox_earcut.triangulate_float64` (with fallback to pure ear clipping), eliminating self-intersections on non-convex soles.
    - Verified outward downward normal orientation ($n_z < 0$) for all base cap triangles.
  - CLI Turbo Pipeline Integration (`scripts/demo.py`):
    - Added `--turbo` flag auto-configuring `max_frames=36`, `max_image_size=960`, `dense=True`, `align_support=True`, `clean_mesh=True`, `remove_floor=True`, `cap_base=True`, and `base_z=0.005`.
    - Added graceful video path resolution falling back to repository candidates (`data/raw/shoe_2.mp4`).
  - Unit Tests:
    - Added `test_colmap_adapter_turbo_flags` and `test_demo_turbo_cli` in `tests/unit/reconstruction/test_colmap_adapter.py`.
    - Total test suite: 240 passed in 4.55s.
- **Empirical Verification (`outputs/turbo_run`)**:
  - Command: `.venv/bin/python scripts/demo.py --video data/raw/shoe_2.mp4 --output-dir outputs/turbo_run --turbo --target-length 280.0 --export-stl`
  - Total end-to-end turnaround: **151.0 seconds** (2.5 minutes, beating < 200s target).
  - Frame extraction: 36 frames downscaled to $540 \times 960$ in 51.8s.
  - Sparse SfM: SIFT GPU extraction + sequential matching + 16-thread mapper in 7.0s.
  - Dense MVS & Meshing: 88.69s (photometric stereo in 25s, fusion 183k points, Poisson mesher 65,666 verts in 1.6s).
  - Canonical Alignment: RANSAC support plane normal $[0.163, -0.541, -0.825]$ rotated to $[0, 0, 1]^T$ at $Z=0$.
  - Phase 3 Cleaning & Planar Slicing: 5,415 `mapbox-earcut` cap faces across 65 loops at $Z=0.005$.
  - Target Scaling: Uniform scaling ($s=22.78428$) to 280.0 mm in float64 memory.
  - Printability Gate: **PASSED** (watertight=True, 0 boundary edges, 0 non-manifold edges, 0 non-manifold vertices, volume=$448,368.5\,\text{mm}^3$).
  - Binary STL Exported: `outputs/stl/cleaned_aligned_meshed-poisson_metric.stl` (86,850 faces, 4,342,584 bytes).
  - JSON Manifest: `outputs/stl/cleaned_aligned_meshed-poisson_metric_manifest.json`.

---



---

## Iteration 019 — Target-Length Uniform CLI Scaling & STL Float32 Quantization Guard
- **Date**: 2026-11-10
- **Milestone**: Phase 4 / Phase 7 — Metric Scaling, In-Memory Uniform Resizing & Manufacturing STL Export
- **Changes Implemented**:
  - Target-Length CLI Argument (`--target-length`):
    - Added `--target-length <float>` in `scripts/demo.py` and `argparse.ArgumentParser` (e.g. `--target-length 280.0` for shoe models).
  - In-Memory Uniform Metric Scaling:
    - In `run_demo()`, after Phase 3 mesh cleanup/capping and when fiducial ArUco scaling is bypassed:
      - Computes uniform scale factor $s = \text{target\_length} / \max(\text{mesh.extents})$.
      - Applies `mesh.apply_scale(s)` in `float64` memory.
      - Re-runs `mesh.merge_vertices()` and `mesh.fix_normals()`.
      - Saves the scaled mesh to `outputs/demo/scaled_<name>.ply`.
      - Passes the in-memory scaled `Trimesh` object directly to `StlExporter`.
  - STL Float32 Quantization Collapse Prevention:
    - Eliminates the 12-14 non-manifold edge collapse caused by exporting small raw photogrammetric models (~2.4 mm extents) into single-precision float32 STL files where adjacent sub-millimeter vertex coordinates snapped together.
    - Verified on 344k-face shoe model scaled to 280.0 mm max extent:
      - Oriented Bounding Box: $290.8 \times 213.1 \times 76.2\,\text{mm}$.
      - Reconstructed Volume: $269,555.2\,\text{mm}^3$.
      - Scale Factor: $117.18321$.
      - Printability Gate: PASSED (watertight = True, manifold = True, non-manifold edges = 0, positive volume).
  - Unit Test Coverage:
    - Added `test_demo_target_length_scaling` in `tests/unit/reconstruction/test_colmap_adapter.py`.
- **Verification**:
  - Full test suite: 228 passed in 3.44s.
  - Export and printability unit tests: 9 passed in 0.29s.
  - End-to-end command executed:
    `.venv/bin/python scripts/demo.py --mesh-only outputs/demo/dense/meshed-poisson.ply --point-cloud outputs/demo/dense/fused.ply --clean-mesh --cap-base --target-length 280.0 --export-stl`
    successfully produced `outputs/stl/cleaned_meshed-poisson_metric.stl` (17.2 MB) and manifest.
- **Next Steps**:
  - Live video capture and accuracy benchmarking against physical shoe measured with digital calipers.

---

## Iteration 022 — Unified Turbo Video-to-3D-Print Pipeline (< 200s Total Runtime Benchmark)
- **Date**: 2026-11-10
- **Milestone**: Phase 1 / Phase 2 / Phase 3 / Phase 4 / Phase 7 / Phase 8 — End-to-End Turbo Pipeline Benchmark Verified
- **Context & Motivation**:
  - Processing hundreds of unconstrained video frames through unoptimized photogrammetry caused 25+ minute bottlenecks, thermal throttling, and memory crashes.
  - Requirement: End-to-end turnaround under 200s (3.5 minutes) from raw smartphone video to a 100% watertight, validated, 2-manifold binary STL.
- **Changes Implemented**:
  - Video Ingest & Downscaling (`src/loom/video/frames.py`, `src/loom/config/models.py`):
    - Added `target_max_dimension: Optional[int] = 960` and `turbo: bool = False` to `VideoConfig`.
    - Downscaled extracted keyframes using `cv2.INTER_AREA` when $\max(H, W) > 960$.
    - In `--turbo` mode, defaulted `max_frames = 36` with even duration striding and Laplacian blur filtering.
  - Live Subprocess Streaming (`src/loom/utils/subprocess.py`):
    - Re-architected `run_subprocess()` with `stream_output=True` using `subprocess.Popen` and daemon pipe reader threads to stream live progress to stdout/stderr while capturing full output.
  - Reconstruction Acceleration (`src/loom/reconstruction/colmap.py`):
    - Added `turbo` flag to `ColmapAdapter.run_matching()`, `run_mapper()`, `run_stereo_fusion()`, and `reconstruct_dense()`.
    - Matching: GPU sequential matching with `overlap=5`, `quadratic_overlap=0`.
    - Mapper: 16 threads, bounded bundle adjustment iterations (`ba_global=12`, `ba_local=10`).
    - Dense MVS: Single-pass photometric stereo (`window_radius=4`, `num_iterations=3`, `geom_consistency=False`, `max_image_size=960`).
    - Meshing: Poisson mesher at depth 9 with `trim=0` directly on `fused.ply` containing native normal vectors.
  - Planar Base Capping with `mapbox-earcut` (`src/loom/mesh/repair.py`):
    - Replaced centroid fan triangulation on base cut loops with `mapbox_earcut.triangulate_float64` (with fallback to pure ear clipping), eliminating self-intersections on non-convex soles.
    - Verified outward downward normal orientation ($n_z < 0$) for all base cap triangles.
  - CLI Turbo Pipeline Integration (`scripts/demo.py`):
    - Added `--turbo` flag auto-configuring `max_frames=36`, `max_image_size=960`, `dense=True`, `align_support=True`, `clean_mesh=True`, `remove_floor=True`, `cap_base=True`, and `base_z=0.005`.
    - Added graceful video path resolution falling back to repository candidates (`data/raw/shoe_2.mp4`).
  - Unit Tests:
    - Added `test_colmap_adapter_turbo_flags` and `test_demo_turbo_cli` in `tests/unit/reconstruction/test_colmap_adapter.py`.
    - Total test suite: 240 passed in 4.55s.
- **Empirical Verification (`outputs/turbo_run`)**:
  - Command: `.venv/bin/python scripts/demo.py --video data/raw/shoe_2.mp4 --output-dir outputs/turbo_run --turbo --target-length 280.0 --export-stl`
  - Total end-to-end turnaround: **151.0 seconds** (2.5 minutes, beating < 200s target).
  - Frame extraction: 36 frames downscaled to $540 \times 960$ in 51.8s.
  - Sparse SfM: SIFT GPU extraction + sequential matching + 16-thread mapper in 7.0s.
  - Dense MVS & Meshing: 88.69s (photometric stereo in 25s, fusion 183k points, Poisson mesher 65,666 verts in 1.6s).
  - Canonical Alignment: RANSAC support plane normal $[0.163, -0.541, -0.825]$ rotated to $[0, 0, 1]^T$ at $Z=0$.
  - Phase 3 Cleaning & Planar Slicing: 5,415 `mapbox-earcut` cap faces across 65 loops at $Z=0.005$.
  - Target Scaling: Uniform scaling ($s=22.78428$) to 280.0 mm in float64 memory.
  - Printability Gate: **PASSED** (watertight=True, 0 boundary edges, 0 non-manifold edges, 0 non-manifold vertices, volume=$448,368.5\,\text{mm}^3$).
  - Binary STL Exported: `outputs/stl/cleaned_aligned_meshed-poisson_metric.stl` (86,850 faces, 4,342,584 bytes).
  - JSON Manifest: `outputs/stl/cleaned_aligned_meshed-poisson_metric_manifest.json`.

---



---

## Iteration 018 — KDTree Point Cloud Distance Culling, Planar Base Slicing & Validated Watertight STL Export
- **Date**: 2026-11-10
- **Milestone**: Phase 3 / Phase 5 / Phase 7 — Robust Geometry Repair, Planar Base Slicing & Validated Manufacturing STL Export
- **Changes Implemented**:
  - KDTree Point Cloud Distance Culling (`cull_by_point_cloud_distance`):
    - Resolved Poisson surface ballooning into unobserved air and connected floor planes.
    - Built a `scipy.spatial.cKDTree` from the dense point cloud (`fused.ply`).
    - Estimated median 2-NN point spacing across a deterministic sample.
    - Culled all mesh faces with vertex distance exceeding $3.5 \times \text{spacing}$ (threshold = 0.00995), removing 440,699 spurious air faces and cleanly detaching the floor plane into a separate component.
  - Floor Separation & Planar Base Capping:
    - Implemented `MeshCleaner.fit_floor_plane_ransac` to estimate the horizontal floor plane equation.
    - Enhanced `MeshRepairer.slice_and_cap_base` to cleanly slice the lower perimeter at $Z_{\text{base}} = Z_{\text{min}} + \text{percentile} \cdot \Delta Z$.
    - Added slight perturbation to slice elevation when vertices lie within $1e-6$ to prevent zero-length cut segments.
    - Capped the underside boundary loop with downward-facing triangles ($\mathbf{n} = (0, 0, -1)$).
  - Figure-8 Loop Decomposition & Non-Manifold Triangulation Prevention:
    - Added `split_into_simple_cycles` to decompose complex figure-8 boundary loops with pinch vertices into simple disjoint vertex cycles.
    - Tracked `existing_face_sets: set[frozenset[int]]` during hole triangulation and base capping to strictly forbid duplicate faces, eliminating non-manifold edges.
    - Implemented multi-pass hole repair when `close_all_holes` is enabled to completely close residual touching boundary loops.
    - Added coincident vertex merging for STL loading in `MeshProcessor.process` to reconstruct topological face adjacency.
    - Reordered `MeshProcessor.process` to execute base capping before defect closure, followed by face winding and outward normal orientation.
  - End-to-End Pipeline & CLI Integration:
    - Integrated point cloud distance culling, floor removal, and base capping into `scripts/demo.py` (`--point-cloud`, `--cap-base`, `--clean-mesh`, `--export-stl`).
    - Verified `PrintabilityGate` validation directly inside `demo.py`: PASSED with 0 boundary edges (watertight = True), 0 non-manifold edges, 0 non-manifold vertices, and positive volume ($0.167514\text{ mm}^3$).
    - Generated binary STL (`cleaned_meshed-poisson_metric.stl`, 344,046 triangles, 17,202,384 bytes) and JSON manifest.
  - Test Suite Expansion:
    - Added `test_cull_mesh_by_point_cloud_distance` and `test_fit_floor_plane_ransac` in `tests/unit/mesh/test_cleanup.py`.
    - Added `test_split_into_simple_cycles` in `tests/unit/mesh/test_repair.py`.
- **Verification**:
  - Full test suite: 227 passed in 3.68s with zero warnings or errors.
  - Standalone and demo CLI runs on real shoe photogrammetric reconstruction (`outputs/demo/dense/meshed-poisson.ply` with `fused.ply`):
    - Raw: 543,013 vertices, 1,084,399 faces.
    - Culled: 357,326 vertices, 643,700 faces.
    - Isolated dominant shoe: 171,731 vertices, 327,276 faces.
    - Base-capped & repaired: 172,009 vertices, 344,046 faces.
    - Printability gate: PASSED (watertight = True, manifold = True, positive volume).
- **Next Steps**:
  - Live capture experiment with physical ArUco fiducial visible in >= 2 frames to measure real-world millimeter dimensional accuracy against calipers.

---

## Iteration 022 — Unified Turbo Video-to-3D-Print Pipeline (< 200s Total Runtime Benchmark)
- **Date**: 2026-11-10
- **Milestone**: Phase 1 / Phase 2 / Phase 3 / Phase 4 / Phase 7 / Phase 8 — End-to-End Turbo Pipeline Benchmark Verified
- **Context & Motivation**:
  - Processing hundreds of unconstrained video frames through unoptimized photogrammetry caused 25+ minute bottlenecks, thermal throttling, and memory crashes.
  - Requirement: End-to-end turnaround under 200s (3.5 minutes) from raw smartphone video to a 100% watertight, validated, 2-manifold binary STL.
- **Changes Implemented**:
  - Video Ingest & Downscaling (`src/loom/video/frames.py`, `src/loom/config/models.py`):
    - Added `target_max_dimension: Optional[int] = 960` and `turbo: bool = False` to `VideoConfig`.
    - Downscaled extracted keyframes using `cv2.INTER_AREA` when $\max(H, W) > 960$.
    - In `--turbo` mode, defaulted `max_frames = 36` with even duration striding and Laplacian blur filtering.
  - Live Subprocess Streaming (`src/loom/utils/subprocess.py`):
    - Re-architected `run_subprocess()` with `stream_output=True` using `subprocess.Popen` and daemon pipe reader threads to stream live progress to stdout/stderr while capturing full output.
  - Reconstruction Acceleration (`src/loom/reconstruction/colmap.py`):
    - Added `turbo` flag to `ColmapAdapter.run_matching()`, `run_mapper()`, `run_stereo_fusion()`, and `reconstruct_dense()`.
    - Matching: GPU sequential matching with `overlap=5`, `quadratic_overlap=0`.
    - Mapper: 16 threads, bounded bundle adjustment iterations (`ba_global=12`, `ba_local=10`).
    - Dense MVS: Single-pass photometric stereo (`window_radius=4`, `num_iterations=3`, `geom_consistency=False`, `max_image_size=960`).
    - Meshing: Poisson mesher at depth 9 with `trim=0` directly on `fused.ply` containing native normal vectors.
  - Planar Base Capping with `mapbox-earcut` (`src/loom/mesh/repair.py`):
    - Replaced centroid fan triangulation on base cut loops with `mapbox_earcut.triangulate_float64` (with fallback to pure ear clipping), eliminating self-intersections on non-convex soles.
    - Verified outward downward normal orientation ($n_z < 0$) for all base cap triangles.
  - CLI Turbo Pipeline Integration (`scripts/demo.py`):
    - Added `--turbo` flag auto-configuring `max_frames=36`, `max_image_size=960`, `dense=True`, `align_support=True`, `clean_mesh=True`, `remove_floor=True`, `cap_base=True`, and `base_z=0.005`.
    - Added graceful video path resolution falling back to repository candidates (`data/raw/shoe_2.mp4`).
  - Unit Tests:
    - Added `test_colmap_adapter_turbo_flags` and `test_demo_turbo_cli` in `tests/unit/reconstruction/test_colmap_adapter.py`.
    - Total test suite: 240 passed in 4.55s.
- **Empirical Verification (`outputs/turbo_run`)**:
  - Command: `.venv/bin/python scripts/demo.py --video data/raw/shoe_2.mp4 --output-dir outputs/turbo_run --turbo --target-length 280.0 --export-stl`
  - Total end-to-end turnaround: **151.0 seconds** (2.5 minutes, beating < 200s target).
  - Frame extraction: 36 frames downscaled to $540 \times 960$ in 51.8s.
  - Sparse SfM: SIFT GPU extraction + sequential matching + 16-thread mapper in 7.0s.
  - Dense MVS & Meshing: 88.69s (photometric stereo in 25s, fusion 183k points, Poisson mesher 65,666 verts in 1.6s).
  - Canonical Alignment: RANSAC support plane normal $[0.163, -0.541, -0.825]$ rotated to $[0, 0, 1]^T$ at $Z=0$.
  - Phase 3 Cleaning & Planar Slicing: 5,415 `mapbox-earcut` cap faces across 65 loops at $Z=0.005$.
  - Target Scaling: Uniform scaling ($s=22.78428$) to 280.0 mm in float64 memory.
  - Printability Gate: **PASSED** (watertight=True, 0 boundary edges, 0 non-manifold edges, 0 non-manifold vertices, volume=$448,368.5\,\text{mm}^3$).
  - Binary STL Exported: `outputs/stl/cleaned_aligned_meshed-poisson_metric.stl` (86,850 faces, 4,342,584 bytes).
  - JSON Manifest: `outputs/stl/cleaned_aligned_meshed-poisson_metric_manifest.json`.

---



---

## Iteration 017 — Memory-Safe Connected Components, Dominant Component Isolation & ArUco Graceful Fallback
- **Date**: 2026-11-10
- **Milestone**: Phase 3 / Phase 4 / Phase 7 — High-Resolution Mesh Repair, Graceful Scaling & Manufacturing Export
- **Changes Implemented**:
  - Memory-Safe Connected Component Slicing:
    - Eliminated `mesh.split(only_watertight=False)` in `MeshComponentAnalyzer` and `MeshCleaner`, which previously allocated ~7 GB of RAM across 495 submeshes on 1M-face meshes and triggered Linux kernel OOM kills.
    - Added `MeshComponentAnalyzer.get_face_components(mesh)` using `trimesh.graph.connected_components(mesh.face_adjacency)` to return numpy face index arrays sorted descending by face count without creating submesh objects.
    - Refactored `MeshComponentAnalyzer.analyze()` to calculate bounding boxes, vertex counts, and areas directly from numpy arrays.
    - Extracted the single target component using `mesh.submesh([target_faces], append=True)`.
  - Dominant Component Isolation & Noise Speck Rejection:
    - Resolved the critical defect where whole-mesh bounding box midpoint selection chose a 122-face noise speck and discarded the 1,035,175-face shoe.
    - Component Selection Logic:
      - Identify large components with > 100,000 faces (or > 20% of total mesh faces AND >= 1,000 faces for models with >= 10,000 faces).
      - Component #0 is the primary object (the shoe).
      - Under NO circumstances can any component with < 1,000 faces be chosen as the target object when large components exist.
      - When `reference_point` is None, default directly to Component #0.
  - Graceful ArUco Fallback:
    - In `ScalingProcessor.process()`, wrapped COLMAP marker triangulation in `try...except ReferenceDetectionError`.
    - When marker ID 0 is observed in < 2 registered views (or reference detection fails) and `raise_on_error=False`:
      - Exports unscaled mesh with `scale_factor = 1.0`.
      - Logs `[WARNING] ArUco marker not observed in registered views. Bypassing metric scaling; preserving photogrammetric units.`.
      - Returns `ScalingResult(status="SKIPPED", scale_factor=1.0)`.
  - CLI `--mesh-only` Shortcut:
    - Added `--mesh-only <path>` to `scripts/demo.py` and `argparse.ArgumentParser`.
    - Bypasses COLMAP binary checking, video ingest, and SfM/MVS reconstruction; runs Phases 3–7 directly on pre-computed meshes.
    - Fixed `dense_source` scoping error in `run_demo()`.
  - Performance & Gate Optimizations:
    - Cached `PrintabilityValidationResult` on `StlExporter` and added `validation_result` parameter to `export()` to eliminate redundant 11-second evaluation passes on 1M triangles when retrying with `enforce_gate=False`.
    - Changed per-loop repair logging in `MeshRepairer` from INFO to DEBUG, eliminating 10,000+ log lines.
  - Added Test Coverage:
    - Added `test_get_face_components_returns_sorted_face_arrays`, `test_filter_strategy_centroid_proximity_default_component_zero`, and `test_filter_strategy_centroid_proximity_rejects_speck_when_large_component_exists` in `tests/unit/mesh/test_components.py`.
    - Added `test_scaling_processor_aruco_graceful_fallback_insufficient_views` in `tests/unit/scaling/test_scaling_processor.py`.
    - Added `test_demo_mesh_only_bypasses_colmap_and_runs_downstream` and `test_demo_main_mesh_only_cli_argument` in `tests/unit/reconstruction/test_colmap_adapter.py`.
- **Verification**:
  - Full test suite: 224 passed in 4.66s.
  - Real mesh execution: `.venv/bin/python scripts/demo.py --mesh-only outputs/demo/dense/meshed-poisson.ply --output-dir outputs/demo_mesh_only` isolated 1,022,663-face shoe, capped base at Z=21.08, and exported 51 MB binary STL `outputs/stl/cleaned_meshed-poisson_metric.stl` and JSON manifest.
- **Next Steps**:
  - Execute end-to-end photogrammetric pipeline on complete captured video sequence with ArUco marker visible in >= 2 frames.
- **Date**: 2026-11-09
- **Milestone**: Phase 2 / Phase 3 — Robust Dense Surface Reconstruction & Poisson Trimming Prevention
- **Changes Implemented**:
  - Resolved Empty Poisson Mesh Culling:
    - Root cause: `colmap poisson_mesher` ran with default `--PoissonMeshing.trim 10`, which pruned 100% of surface polygons on low-parallax boundary regions, generating a 248-byte header with 0 vertices and crashing Phase 3 geometry loading.
    - Updated `ColmapAdapter.build_poisson_mesher_args()` and added `run_poisson_mesher()` with:
      - `--PoissonMeshing.depth 10` (octree maximum resolution).
      - `--PoissonMeshing.trim 0` (completely disables aggressive SurfaceTrimmer deletion).
      - `--PoissonMeshing.point_weight 1.0` (preserves input point surface constraints).
  - Increased Stereo Fusion Point Cloud Density:
    - Root cause: default `--StereoFusion.min_num_pixels 5` culled valid surface points visible across 2-4 frames in small-baseline video captures, reducing point yield below 50,000.
    - Updated `ColmapAdapter.build_stereo_fusion_args()` and added `run_stereo_fusion()` with:
      - `--StereoFusion.min_num_pixels 2` (preserves points seen across 2-3 consistent views).
      - `--StereoFusion.max_image_size 1600` (safeguards 8 GB VRAM buffer).
  - Dense Delaunay Mesher Fallback Pipeline:
    - Added `run_delaunay_mesher()` and updated `reconstruct_dense()`:
      - Verifies `read_ply_vertex_count(poisson_ply) > 0`.
      - If Poisson mesher produces 0 vertices or crashes, automatically triggers fallback to `colmap delaunay_mesher --input_type dense --input_path <workspace> --output_path <workspace>/meshed-delaunay.ply`.
      - Populates `delaunay_mesh_path` on `ColmapDenseArtifact` and forwards the valid Delaunay mesh to downstream Phase 3 geometry repair.
  - CLI & Demo Script Integration:
    - Added `--min-num-pixels` argument (default: 2) in `scripts/demo.py` and forwarded to `reconstruct_dense()`.
  - Added Test Coverage:
    - Updated `test_all_argument_builders` and `test_reconstruct_dense_executes_sequential_pipeline`.
    - Added `test_reconstruct_dense_empty_poisson_triggers_delaunay_fallback`, `test_reconstruct_dense_poisson_error_triggers_delaunay_fallback`, and `test_colmap_direct_stage_runners` in `tests/unit/reconstruction/test_colmap_adapter.py`.
- **Verification**:
  - `pytest tests/unit/reconstruction/test_colmap_adapter.py`: 24 passed in 0.21s.
  - Full test suite: 218 passed in 3.60s.
  - `.venv/bin/python scripts/demo.py --help`: Verified `--min-num-pixels 2` CLI option.
- **Next Steps**:
  - Execute end-to-end reconstruction on real video data (`data/raw/shoe_2.mp4`) with dense stereo and manufacturing STL export.

---

## Iteration 022 — Unified Turbo Video-to-3D-Print Pipeline (< 200s Total Runtime Benchmark)
- **Date**: 2026-11-10
- **Milestone**: Phase 1 / Phase 2 / Phase 3 / Phase 4 / Phase 7 / Phase 8 — End-to-End Turbo Pipeline Benchmark Verified
- **Context & Motivation**:
  - Processing hundreds of unconstrained video frames through unoptimized photogrammetry caused 25+ minute bottlenecks, thermal throttling, and memory crashes.
  - Requirement: End-to-end turnaround under 200s (3.5 minutes) from raw smartphone video to a 100% watertight, validated, 2-manifold binary STL.
- **Changes Implemented**:
  - Video Ingest & Downscaling (`src/loom/video/frames.py`, `src/loom/config/models.py`):
    - Added `target_max_dimension: Optional[int] = 960` and `turbo: bool = False` to `VideoConfig`.
    - Downscaled extracted keyframes using `cv2.INTER_AREA` when $\max(H, W) > 960$.
    - In `--turbo` mode, defaulted `max_frames = 36` with even duration striding and Laplacian blur filtering.
  - Live Subprocess Streaming (`src/loom/utils/subprocess.py`):
    - Re-architected `run_subprocess()` with `stream_output=True` using `subprocess.Popen` and daemon pipe reader threads to stream live progress to stdout/stderr while capturing full output.
  - Reconstruction Acceleration (`src/loom/reconstruction/colmap.py`):
    - Added `turbo` flag to `ColmapAdapter.run_matching()`, `run_mapper()`, `run_stereo_fusion()`, and `reconstruct_dense()`.
    - Matching: GPU sequential matching with `overlap=5`, `quadratic_overlap=0`.
    - Mapper: 16 threads, bounded bundle adjustment iterations (`ba_global=12`, `ba_local=10`).
    - Dense MVS: Single-pass photometric stereo (`window_radius=4`, `num_iterations=3`, `geom_consistency=False`, `max_image_size=960`).
    - Meshing: Poisson mesher at depth 9 with `trim=0` directly on `fused.ply` containing native normal vectors.
  - Planar Base Capping with `mapbox-earcut` (`src/loom/mesh/repair.py`):
    - Replaced centroid fan triangulation on base cut loops with `mapbox_earcut.triangulate_float64` (with fallback to pure ear clipping), eliminating self-intersections on non-convex soles.
    - Verified outward downward normal orientation ($n_z < 0$) for all base cap triangles.
  - CLI Turbo Pipeline Integration (`scripts/demo.py`):
    - Added `--turbo` flag auto-configuring `max_frames=36`, `max_image_size=960`, `dense=True`, `align_support=True`, `clean_mesh=True`, `remove_floor=True`, `cap_base=True`, and `base_z=0.005`.
    - Added graceful video path resolution falling back to repository candidates (`data/raw/shoe_2.mp4`).
  - Unit Tests:
    - Added `test_colmap_adapter_turbo_flags` and `test_demo_turbo_cli` in `tests/unit/reconstruction/test_colmap_adapter.py`.
    - Total test suite: 240 passed in 4.55s.
- **Empirical Verification (`outputs/turbo_run`)**:
  - Command: `.venv/bin/python scripts/demo.py --video data/raw/shoe_2.mp4 --output-dir outputs/turbo_run --turbo --target-length 280.0 --export-stl`
  - Total end-to-end turnaround: **151.0 seconds** (2.5 minutes, beating < 200s target).
  - Frame extraction: 36 frames downscaled to $540 \times 960$ in 51.8s.
  - Sparse SfM: SIFT GPU extraction + sequential matching + 16-thread mapper in 7.0s.
  - Dense MVS & Meshing: 88.69s (photometric stereo in 25s, fusion 183k points, Poisson mesher 65,666 verts in 1.6s).
  - Canonical Alignment: RANSAC support plane normal $[0.163, -0.541, -0.825]$ rotated to $[0, 0, 1]^T$ at $Z=0$.
  - Phase 3 Cleaning & Planar Slicing: 5,415 `mapbox-earcut` cap faces across 65 loops at $Z=0.005$.
  - Target Scaling: Uniform scaling ($s=22.78428$) to 280.0 mm in float64 memory.
  - Printability Gate: **PASSED** (watertight=True, 0 boundary edges, 0 non-manifold edges, 0 non-manifold vertices, volume=$448,368.5\,\text{mm}^3$).
  - Binary STL Exported: `outputs/stl/cleaned_aligned_meshed-poisson_metric.stl` (86,850 faces, 4,342,584 bytes).
  - JSON Manifest: `outputs/stl/cleaned_aligned_meshed-poisson_metric_manifest.json`.

---



---

## Iteration 015 — Video Turnaround Optimization (Laplacian Blur Culling, Sequential Matching & Thread Pinning)
- **Date**: 2026-11-09
- **Milestone**: Phase 1 / Phase 2 — Video Ingest Culling & SfM Turnaround Optimization (< 4 min)
- **Changes Implemented**:
  - Implemented optical blur rejection and keyframe culling in `src/loom/video/frames.py`:
    - Added `compute_laplacian_variance()` measuring $\text{Var}(\nabla^2 I) = \text{cv2.Laplacian}(I, \text{cv2.CV_64F}).\text{var}()$.
    - Added `find_nearest_sharp_frame()` scanning adjacent alternating offsets ($\pm 1, \pm 2, \ldots, \pm 10$) to replace blurry candidate frames with the nearest sharp alternative.
    - Updated `FrameExtractor.extract()` to cap default keyframes to 75 and evenly stride candidates across video duration when `source_frame_count > max_frames`.
    - Added `blur_threshold: float = 20.0` in `VideoConfig` and updated `configs/default.yaml` `max_frames: 75`.
  - Upgraded COLMAP sequential matching and Ceres BA bounds in `src/loom/reconstruction/colmap.py`:
    - Enhanced `run_matching()` with explicit `matching_mode="sequential"` routing to `colmap sequential_matcher` with `--SequentialMatching.overlap 10`, `--SequentialMatching.quadratic_overlap 1`, `--SequentialMatching.loop_detection 1`, `--FeatureMatching.use_gpu 1`, and `--FeatureMatching.gpu_index 0`.
    - Enhanced `build_mapper_args()` and `run_mapper()` with `--Mapper.num_threads 16`, `--Mapper.ba_global_max_num_iterations 20`, and `--Mapper.ba_local_max_num_iterations 15`.
  - Updated `scripts/demo.py`:
    - Adjusted default `--max-frames` from 300 to 75.
    - Added automated purging of stale `outputs/demo/database.db` and `outputs/demo/images/` before running SfM to eliminate SQLite file locking and stale feature match corruption across runs.
    - Automatically routes `--video` inputs through `matching_mode="sequential"`.
  - Turnaround Impact:
    - Reduced matching pairs by >85% and eliminated unbounded Ceres local/global refinement stalls, accelerating sparse SfM turnaround from ~30 minutes to under 4 minutes on 1080p video.
  - Added comprehensive test suite:
    - Added `test_compute_laplacian_variance`, `test_frame_extraction_blur_rejection_and_fallback`, and `test_frame_extraction_even_striding` in `tests/unit/video/test_frames.py`.
    - Updated `test_mapper_args_thread_scaling`, `test_run_matching_invokes_correct_matcher`, and `test_run_mapper_invokes_colmap_mapper` in `tests/unit/reconstruction/test_colmap_adapter.py`.
- **Verification**:
  - `pytest tests/unit/video/test_frames.py tests/unit/reconstruction/test_colmap_adapter.py`: 28 passed in 0.76s.
  - Full test suite: 215 passed in 3.36s.
  - `.venv/bin/python scripts/demo.py --help`: Verified `--max-frames 75` and options.
- **Next Steps**:
  - Execute end-to-end photogrammetry and STL export on `data/raw/shoe_2.mp4`.

---

## Iteration 022 — Unified Turbo Video-to-3D-Print Pipeline (< 200s Total Runtime Benchmark)
- **Date**: 2026-11-10
- **Milestone**: Phase 1 / Phase 2 / Phase 3 / Phase 4 / Phase 7 / Phase 8 — End-to-End Turbo Pipeline Benchmark Verified
- **Context & Motivation**:
  - Processing hundreds of unconstrained video frames through unoptimized photogrammetry caused 25+ minute bottlenecks, thermal throttling, and memory crashes.
  - Requirement: End-to-end turnaround under 200s (3.5 minutes) from raw smartphone video to a 100% watertight, validated, 2-manifold binary STL.
- **Changes Implemented**:
  - Video Ingest & Downscaling (`src/loom/video/frames.py`, `src/loom/config/models.py`):
    - Added `target_max_dimension: Optional[int] = 960` and `turbo: bool = False` to `VideoConfig`.
    - Downscaled extracted keyframes using `cv2.INTER_AREA` when $\max(H, W) > 960$.
    - In `--turbo` mode, defaulted `max_frames = 36` with even duration striding and Laplacian blur filtering.
  - Live Subprocess Streaming (`src/loom/utils/subprocess.py`):
    - Re-architected `run_subprocess()` with `stream_output=True` using `subprocess.Popen` and daemon pipe reader threads to stream live progress to stdout/stderr while capturing full output.
  - Reconstruction Acceleration (`src/loom/reconstruction/colmap.py`):
    - Added `turbo` flag to `ColmapAdapter.run_matching()`, `run_mapper()`, `run_stereo_fusion()`, and `reconstruct_dense()`.
    - Matching: GPU sequential matching with `overlap=5`, `quadratic_overlap=0`.
    - Mapper: 16 threads, bounded bundle adjustment iterations (`ba_global=12`, `ba_local=10`).
    - Dense MVS: Single-pass photometric stereo (`window_radius=4`, `num_iterations=3`, `geom_consistency=False`, `max_image_size=960`).
    - Meshing: Poisson mesher at depth 9 with `trim=0` directly on `fused.ply` containing native normal vectors.
  - Planar Base Capping with `mapbox-earcut` (`src/loom/mesh/repair.py`):
    - Replaced centroid fan triangulation on base cut loops with `mapbox_earcut.triangulate_float64` (with fallback to pure ear clipping), eliminating self-intersections on non-convex soles.
    - Verified outward downward normal orientation ($n_z < 0$) for all base cap triangles.
  - CLI Turbo Pipeline Integration (`scripts/demo.py`):
    - Added `--turbo` flag auto-configuring `max_frames=36`, `max_image_size=960`, `dense=True`, `align_support=True`, `clean_mesh=True`, `remove_floor=True`, `cap_base=True`, and `base_z=0.005`.
    - Added graceful video path resolution falling back to repository candidates (`data/raw/shoe_2.mp4`).
  - Unit Tests:
    - Added `test_colmap_adapter_turbo_flags` and `test_demo_turbo_cli` in `tests/unit/reconstruction/test_colmap_adapter.py`.
    - Total test suite: 240 passed in 4.55s.
- **Empirical Verification (`outputs/turbo_run`)**:
  - Command: `.venv/bin/python scripts/demo.py --video data/raw/shoe_2.mp4 --output-dir outputs/turbo_run --turbo --target-length 280.0 --export-stl`
  - Total end-to-end turnaround: **151.0 seconds** (2.5 minutes, beating < 200s target).
  - Frame extraction: 36 frames downscaled to $540 \times 960$ in 51.8s.
  - Sparse SfM: SIFT GPU extraction + sequential matching + 16-thread mapper in 7.0s.
  - Dense MVS & Meshing: 88.69s (photometric stereo in 25s, fusion 183k points, Poisson mesher 65,666 verts in 1.6s).
  - Canonical Alignment: RANSAC support plane normal $[0.163, -0.541, -0.825]$ rotated to $[0, 0, 1]^T$ at $Z=0$.
  - Phase 3 Cleaning & Planar Slicing: 5,415 `mapbox-earcut` cap faces across 65 loops at $Z=0.005$.
  - Target Scaling: Uniform scaling ($s=22.78428$) to 280.0 mm in float64 memory.
  - Printability Gate: **PASSED** (watertight=True, 0 boundary edges, 0 non-manifold edges, 0 non-manifold vertices, volume=$448,368.5\,\text{mm}^3$).
  - Binary STL Exported: `outputs/stl/cleaned_aligned_meshed-poisson_metric.stl` (86,850 faces, 4,342,584 bytes).
  - JSON Manifest: `outputs/stl/cleaned_aligned_meshed-poisson_metric_manifest.json`.

---



---

## Iteration 014 — Sequential Video Feature Matching and Multi-Threaded Mapper Scaling for COLMAP
- **Date**: 2026-11-09
- **Milestone**: Phase 2 / Phase 3 — Reconstruction Acceleration & Hardware Thread Scaling
- **Changes Implemented**:
  - Implemented sequential matching and mapper argument builders in `src/loom/reconstruction/colmap.py`:
    - `build_sequential_matcher_args()`: configured with `--SequentialMatching.overlap 10`, `--SequentialMatching.quadratic_overlap 1`, `--SequentialMatching.loop_detection 1`, `--FeatureMatching.use_gpu 1`, and `--FeatureMatching.gpu_index 0`.
    - `build_mapper_args()`: configured with `--Mapper.num_threads 16` (to saturate 16-thread Ryzen 7 CPU) and `--Mapper.ba_global_max_num_iterations 20` (to avoid diminishing-returns BA iterations).
    - Added `run_matching()` and `run_mapper()` methods on `ColmapAdapter`.
    - Updated `reconstruct()` to automatically use `run_matching(..., sequential=True)` when processing video inputs or when `sequential=True` is requested.
  - Updated `src/loom/reconstruction/models.py`:
    - Added `sequential: bool = False` to `ReconstructionJobConfig`.
  - Updated `scripts/demo.py`:
    - Adjusted default `--max-frames` for video ingest from 300 to 80.
    - Added `--sequential` CLI flag and automatically forwards `sequential=True` to `ReconstructionJobConfig` and `adapter.reconstruct()` when video inputs are provided.
  - Added unit tests in `tests/unit/reconstruction/test_colmap_adapter.py`:
    - Verified `build_sequential_matcher_args`, `build_mapper_args`, `run_matching`, `run_mapper`, `reconstruct()` sequential routing, and `scripts/demo.py` video contract.
- **Verification**:
  - `pytest tests/unit/reconstruction/test_colmap_adapter.py`: 21 passed in 0.21s.
  - Full test suite: 212 passed in 3.37s.
  - `python scripts/demo.py --help`: Verified `--max-frames` default 80 and `--sequential` flag.
- **Next Steps**:
  - Execute live reconstruction on `data/raw/shoe_2.mp4`.

---

## Iteration 022 — Unified Turbo Video-to-3D-Print Pipeline (< 200s Total Runtime Benchmark)
- **Date**: 2026-11-10
- **Milestone**: Phase 1 / Phase 2 / Phase 3 / Phase 4 / Phase 7 / Phase 8 — End-to-End Turbo Pipeline Benchmark Verified
- **Context & Motivation**:
  - Processing hundreds of unconstrained video frames through unoptimized photogrammetry caused 25+ minute bottlenecks, thermal throttling, and memory crashes.
  - Requirement: End-to-end turnaround under 200s (3.5 minutes) from raw smartphone video to a 100% watertight, validated, 2-manifold binary STL.
- **Changes Implemented**:
  - Video Ingest & Downscaling (`src/loom/video/frames.py`, `src/loom/config/models.py`):
    - Added `target_max_dimension: Optional[int] = 960` and `turbo: bool = False` to `VideoConfig`.
    - Downscaled extracted keyframes using `cv2.INTER_AREA` when $\max(H, W) > 960$.
    - In `--turbo` mode, defaulted `max_frames = 36` with even duration striding and Laplacian blur filtering.
  - Live Subprocess Streaming (`src/loom/utils/subprocess.py`):
    - Re-architected `run_subprocess()` with `stream_output=True` using `subprocess.Popen` and daemon pipe reader threads to stream live progress to stdout/stderr while capturing full output.
  - Reconstruction Acceleration (`src/loom/reconstruction/colmap.py`):
    - Added `turbo` flag to `ColmapAdapter.run_matching()`, `run_mapper()`, `run_stereo_fusion()`, and `reconstruct_dense()`.
    - Matching: GPU sequential matching with `overlap=5`, `quadratic_overlap=0`.
    - Mapper: 16 threads, bounded bundle adjustment iterations (`ba_global=12`, `ba_local=10`).
    - Dense MVS: Single-pass photometric stereo (`window_radius=4`, `num_iterations=3`, `geom_consistency=False`, `max_image_size=960`).
    - Meshing: Poisson mesher at depth 9 with `trim=0` directly on `fused.ply` containing native normal vectors.
  - Planar Base Capping with `mapbox-earcut` (`src/loom/mesh/repair.py`):
    - Replaced centroid fan triangulation on base cut loops with `mapbox_earcut.triangulate_float64` (with fallback to pure ear clipping), eliminating self-intersections on non-convex soles.
    - Verified outward downward normal orientation ($n_z < 0$) for all base cap triangles.
  - CLI Turbo Pipeline Integration (`scripts/demo.py`):
    - Added `--turbo` flag auto-configuring `max_frames=36`, `max_image_size=960`, `dense=True`, `align_support=True`, `clean_mesh=True`, `remove_floor=True`, `cap_base=True`, and `base_z=0.005`.
    - Added graceful video path resolution falling back to repository candidates (`data/raw/shoe_2.mp4`).
  - Unit Tests:
    - Added `test_colmap_adapter_turbo_flags` and `test_demo_turbo_cli` in `tests/unit/reconstruction/test_colmap_adapter.py`.
    - Total test suite: 240 passed in 4.55s.
- **Empirical Verification (`outputs/turbo_run`)**:
  - Command: `.venv/bin/python scripts/demo.py --video data/raw/shoe_2.mp4 --output-dir outputs/turbo_run --turbo --target-length 280.0 --export-stl`
  - Total end-to-end turnaround: **151.0 seconds** (2.5 minutes, beating < 200s target).
  - Frame extraction: 36 frames downscaled to $540 \times 960$ in 51.8s.
  - Sparse SfM: SIFT GPU extraction + sequential matching + 16-thread mapper in 7.0s.
  - Dense MVS & Meshing: 88.69s (photometric stereo in 25s, fusion 183k points, Poisson mesher 65,666 verts in 1.6s).
  - Canonical Alignment: RANSAC support plane normal $[0.163, -0.541, -0.825]$ rotated to $[0, 0, 1]^T$ at $Z=0$.
  - Phase 3 Cleaning & Planar Slicing: 5,415 `mapbox-earcut` cap faces across 65 loops at $Z=0.005$.
  - Target Scaling: Uniform scaling ($s=22.78428$) to 280.0 mm in float64 memory.
  - Printability Gate: **PASSED** (watertight=True, 0 boundary edges, 0 non-manifold edges, 0 non-manifold vertices, volume=$448,368.5\,\text{mm}^3$).
  - Binary STL Exported: `outputs/stl/cleaned_aligned_meshed-poisson_metric.stl` (86,850 faces, 4,342,584 bytes).
  - JSON Manifest: `outputs/stl/cleaned_aligned_meshed-poisson_metric_manifest.json`.

---



---

## Iteration 013 — FrameExtractor Interface Unification and Video Ingest Integration in Demo Runner
- **Date**: 2026-11-09
- **Milestone**: Phase 1 / Phase 2 — Video Ingest & Reconstruction Integration
- **Changes Implemented**:
  - Unified `FrameExtractor` interface in `src/loom/video/frames.py`:
    - Added defensive method alias `extract_all()` mapping to `extract(video_path, output_dir)` to ensure backward and forward interface compatibility.
    - Preserved exact typed return `FrameSetArtifact` with properties `frames_dir`, `frame_paths`, `total_extracted`, and `metadata`.
  - Updated `scripts/demo.py`:
    - Fixed frame extraction invocation from `extractor.extract_all(...)` to `frame_artifact = extractor.extract(video_path=video_path, output_dir=extracted_dir)`.
    - Corrected active images directory routing to `active_images_dir = frame_artifact.frames_dir`.
    - Added missing import of `ReconstructionJobConfig` from `loom.reconstruction.models`.
    - Added CLI configuration arguments for frame sampling: `--sample-interval`, `--max-frames`, and `--target-fps`.
    - Implemented automatic sparse SfM model generation via `ColmapAdapter.reconstruct()` if `--sparse-dir` is not explicitly supplied when `--video` or `--images` is passed.
- **Verification**:
  - `pytest tests/unit/video/test_frames.py tests/unit/pipeline/`: 15 passed in 0.43s.
  - Full test suite: 206 passed in 4.01s.
  - `python scripts/demo.py --help`: Verified that video extraction flags and contracts are correctly exposed and parsed.
- **Next Steps**:
  - Execute live photogrammetry run on `data/raw/shoe_2.mp4` with native CUDA COLMAP.

---

## Iteration 022 — Unified Turbo Video-to-3D-Print Pipeline (< 200s Total Runtime Benchmark)
- **Date**: 2026-11-10
- **Milestone**: Phase 1 / Phase 2 / Phase 3 / Phase 4 / Phase 7 / Phase 8 — End-to-End Turbo Pipeline Benchmark Verified
- **Context & Motivation**:
  - Processing hundreds of unconstrained video frames through unoptimized photogrammetry caused 25+ minute bottlenecks, thermal throttling, and memory crashes.
  - Requirement: End-to-end turnaround under 200s (3.5 minutes) from raw smartphone video to a 100% watertight, validated, 2-manifold binary STL.
- **Changes Implemented**:
  - Video Ingest & Downscaling (`src/loom/video/frames.py`, `src/loom/config/models.py`):
    - Added `target_max_dimension: Optional[int] = 960` and `turbo: bool = False` to `VideoConfig`.
    - Downscaled extracted keyframes using `cv2.INTER_AREA` when $\max(H, W) > 960$.
    - In `--turbo` mode, defaulted `max_frames = 36` with even duration striding and Laplacian blur filtering.
  - Live Subprocess Streaming (`src/loom/utils/subprocess.py`):
    - Re-architected `run_subprocess()` with `stream_output=True` using `subprocess.Popen` and daemon pipe reader threads to stream live progress to stdout/stderr while capturing full output.
  - Reconstruction Acceleration (`src/loom/reconstruction/colmap.py`):
    - Added `turbo` flag to `ColmapAdapter.run_matching()`, `run_mapper()`, `run_stereo_fusion()`, and `reconstruct_dense()`.
    - Matching: GPU sequential matching with `overlap=5`, `quadratic_overlap=0`.
    - Mapper: 16 threads, bounded bundle adjustment iterations (`ba_global=12`, `ba_local=10`).
    - Dense MVS: Single-pass photometric stereo (`window_radius=4`, `num_iterations=3`, `geom_consistency=False`, `max_image_size=960`).
    - Meshing: Poisson mesher at depth 9 with `trim=0` directly on `fused.ply` containing native normal vectors.
  - Planar Base Capping with `mapbox-earcut` (`src/loom/mesh/repair.py`):
    - Replaced centroid fan triangulation on base cut loops with `mapbox_earcut.triangulate_float64` (with fallback to pure ear clipping), eliminating self-intersections on non-convex soles.
    - Verified outward downward normal orientation ($n_z < 0$) for all base cap triangles.
  - CLI Turbo Pipeline Integration (`scripts/demo.py`):
    - Added `--turbo` flag auto-configuring `max_frames=36`, `max_image_size=960`, `dense=True`, `align_support=True`, `clean_mesh=True`, `remove_floor=True`, `cap_base=True`, and `base_z=0.005`.
    - Added graceful video path resolution falling back to repository candidates (`data/raw/shoe_2.mp4`).
  - Unit Tests:
    - Added `test_colmap_adapter_turbo_flags` and `test_demo_turbo_cli` in `tests/unit/reconstruction/test_colmap_adapter.py`.
    - Total test suite: 240 passed in 4.55s.
- **Empirical Verification (`outputs/turbo_run`)**:
  - Command: `.venv/bin/python scripts/demo.py --video data/raw/shoe_2.mp4 --output-dir outputs/turbo_run --turbo --target-length 280.0 --export-stl`
  - Total end-to-end turnaround: **151.0 seconds** (2.5 minutes, beating < 200s target).
  - Frame extraction: 36 frames downscaled to $540 \times 960$ in 51.8s.
  - Sparse SfM: SIFT GPU extraction + sequential matching + 16-thread mapper in 7.0s.
  - Dense MVS & Meshing: 88.69s (photometric stereo in 25s, fusion 183k points, Poisson mesher 65,666 verts in 1.6s).
  - Canonical Alignment: RANSAC support plane normal $[0.163, -0.541, -0.825]$ rotated to $[0, 0, 1]^T$ at $Z=0$.
  - Phase 3 Cleaning & Planar Slicing: 5,415 `mapbox-earcut` cap faces across 65 loops at $Z=0.005$.
  - Target Scaling: Uniform scaling ($s=22.78428$) to 280.0 mm in float64 memory.
  - Printability Gate: **PASSED** (watertight=True, 0 boundary edges, 0 non-manifold edges, 0 non-manifold vertices, volume=$448,368.5\,\text{mm}^3$).
  - Binary STL Exported: `outputs/stl/cleaned_aligned_meshed-poisson_metric.stl` (86,850 faces, 4,342,584 bytes).
  - JSON Manifest: `outputs/stl/cleaned_aligned_meshed-poisson_metric_manifest.json`.

---



---

## Iteration 012 — Physical Dimension Measurement, Manufacturing Printability Gate, and Validated STL Export
- **Date**: 2026-11-09
- **Milestone**: Phase 5 / Phase 6 / Phase 7 — Dimensional Validation & Manufacturing-Ready Export
- **Changes Implemented**:
  - Implemented physical dimension and oriented bounding box (OBB) measurement in `src/loom/validation/dimensions.py`:
    - `compute_bounding_box()` measures exact Axis-Aligned Bounding Box (AABB) extents returning typed `BoundingBox3D`.
    - `compute_principal_dimensions()` calculates minimum-volume Oriented Bounding Box (OBB) principal dimensions (Length, Width, Height in physical mm with $L \ge W \ge H$).
    - Implemented robust PCA covariance fallback for planar or degenerate geometries, eliminating any dependency on `networkx`.
  - Implemented manufacturing readiness printability verification in `src/loom/printability/`:
    - `WatertightChecker`: verifies closed 2-manifold surface, computes boundary edge counts via `np.unique` edge frequencies (`boundary_edges == 0`), and checks positive volume ($V > 0.0\text{ mm}^3$).
    - `ManifoldChecker`: verifies edge manifoldness (`non_manifold_edges == 0`) and vertex manifoldness using pure topological 1-ring BFS component analysis to catch pinched apexes (`non_manifold_vertices == 0`).
    - `PrintabilityGate`: consolidated gate validating watertightness, manifoldness, and positive volume, raising `PrintabilityValidationError` on violations.
  - Implemented manufacturing-ready binary STL export in `src/loom/export/stl.py` & `src/loom/export/manifest.py`:
    - `StlExporter`: exports binary STL files to `outputs/stl/<model_name>_metric.stl` with an enforced pre-export printability gate.
    - Writes machine-readable JSON build manifest with OBB bounding box dimensions ($L, W, H$), volume ($mm^3$), triangle count, and SHA-256 checksum.
  - Updated `scripts/demo.py`:
    - Added `--export-stl` and `--stl-dir` CLI flags.
    - Automatically executes manufacturing readiness checks and exports validated binary STL and build manifests when flagged.
  - Added comprehensive test suite:
    - Added `tests/unit/validation/test_dimensions.py` covering AABB and rotated OBB measurements, and PCA fallback on planar geometry.
    - Added `tests/unit/printability/test_printability_gate.py` covering watertightness, non-manifold edge detection, pinched vertex detection, and gate rejection.
    - Added `tests/unit/export/test_stl_export.py` covering binary STL structure (80-byte header, uint32 triangle count), JSON build manifests, and gate enforcement.
- **Verification**:
  - `pytest tests/unit/validation/ tests/unit/printability/ tests/unit/export/`: 15 passed in 0.49s.
  - Full test suite: 206 passed in 3.97s.
  - `python scripts/demo.py --help`: Verified CLI flags `--export-stl` and `--stl-dir`.
- **Next Steps**:
  - Execute end-to-end photogrammetry and validated STL export on physical shoe video with ArUco marker.

---

## Iteration 022 — Unified Turbo Video-to-3D-Print Pipeline (< 200s Total Runtime Benchmark)
- **Date**: 2026-11-10
- **Milestone**: Phase 1 / Phase 2 / Phase 3 / Phase 4 / Phase 7 / Phase 8 — End-to-End Turbo Pipeline Benchmark Verified
- **Context & Motivation**:
  - Processing hundreds of unconstrained video frames through unoptimized photogrammetry caused 25+ minute bottlenecks, thermal throttling, and memory crashes.
  - Requirement: End-to-end turnaround under 200s (3.5 minutes) from raw smartphone video to a 100% watertight, validated, 2-manifold binary STL.
- **Changes Implemented**:
  - Video Ingest & Downscaling (`src/loom/video/frames.py`, `src/loom/config/models.py`):
    - Added `target_max_dimension: Optional[int] = 960` and `turbo: bool = False` to `VideoConfig`.
    - Downscaled extracted keyframes using `cv2.INTER_AREA` when $\max(H, W) > 960$.
    - In `--turbo` mode, defaulted `max_frames = 36` with even duration striding and Laplacian blur filtering.
  - Live Subprocess Streaming (`src/loom/utils/subprocess.py`):
    - Re-architected `run_subprocess()` with `stream_output=True` using `subprocess.Popen` and daemon pipe reader threads to stream live progress to stdout/stderr while capturing full output.
  - Reconstruction Acceleration (`src/loom/reconstruction/colmap.py`):
    - Added `turbo` flag to `ColmapAdapter.run_matching()`, `run_mapper()`, `run_stereo_fusion()`, and `reconstruct_dense()`.
    - Matching: GPU sequential matching with `overlap=5`, `quadratic_overlap=0`.
    - Mapper: 16 threads, bounded bundle adjustment iterations (`ba_global=12`, `ba_local=10`).
    - Dense MVS: Single-pass photometric stereo (`window_radius=4`, `num_iterations=3`, `geom_consistency=False`, `max_image_size=960`).
    - Meshing: Poisson mesher at depth 9 with `trim=0` directly on `fused.ply` containing native normal vectors.
  - Planar Base Capping with `mapbox-earcut` (`src/loom/mesh/repair.py`):
    - Replaced centroid fan triangulation on base cut loops with `mapbox_earcut.triangulate_float64` (with fallback to pure ear clipping), eliminating self-intersections on non-convex soles.
    - Verified outward downward normal orientation ($n_z < 0$) for all base cap triangles.
  - CLI Turbo Pipeline Integration (`scripts/demo.py`):
    - Added `--turbo` flag auto-configuring `max_frames=36`, `max_image_size=960`, `dense=True`, `align_support=True`, `clean_mesh=True`, `remove_floor=True`, `cap_base=True`, and `base_z=0.005`.
    - Added graceful video path resolution falling back to repository candidates (`data/raw/shoe_2.mp4`).
  - Unit Tests:
    - Added `test_colmap_adapter_turbo_flags` and `test_demo_turbo_cli` in `tests/unit/reconstruction/test_colmap_adapter.py`.
    - Total test suite: 240 passed in 4.55s.
- **Empirical Verification (`outputs/turbo_run`)**:
  - Command: `.venv/bin/python scripts/demo.py --video data/raw/shoe_2.mp4 --output-dir outputs/turbo_run --turbo --target-length 280.0 --export-stl`
  - Total end-to-end turnaround: **151.0 seconds** (2.5 minutes, beating < 200s target).
  - Frame extraction: 36 frames downscaled to $540 \times 960$ in 51.8s.
  - Sparse SfM: SIFT GPU extraction + sequential matching + 16-thread mapper in 7.0s.
  - Dense MVS & Meshing: 88.69s (photometric stereo in 25s, fusion 183k points, Poisson mesher 65,666 verts in 1.6s).
  - Canonical Alignment: RANSAC support plane normal $[0.163, -0.541, -0.825]$ rotated to $[0, 0, 1]^T$ at $Z=0$.
  - Phase 3 Cleaning & Planar Slicing: 5,415 `mapbox-earcut` cap faces across 65 loops at $Z=0.005$.
  - Target Scaling: Uniform scaling ($s=22.78428$) to 280.0 mm in float64 memory.
  - Printability Gate: **PASSED** (watertight=True, 0 boundary edges, 0 non-manifold edges, 0 non-manifold vertices, volume=$448,368.5\,\text{mm}^3$).
  - Binary STL Exported: `outputs/stl/cleaned_aligned_meshed-poisson_metric.stl` (86,850 faces, 4,342,584 bytes).
  - JSON Manifest: `outputs/stl/cleaned_aligned_meshed-poisson_metric_manifest.json`.

---



---

## Iteration 011 — 2D-to-3D ArUco Triangulation and Scaling Pipeline
- **Date**: 2026-11-09
- **Milestone**: Phase 4 — Metric Grounding & 2D-to-3D Photogrammetric Scaling
- **Changes Implemented**:
  - Implemented COLMAP binary and text model parsing in `src/loom/scaling/aruco.py`:
    - Added `ColmapCamera` and `ColmapImage` data models with `qvec_to_rotmat()` quaternion conversion.
    - Added parser methods `read_colmap_cameras_bin()`, `read_colmap_cameras_text()`, `read_colmap_images_bin()`, and `read_colmap_images_text()`.
    - Added `load_colmap_model()` supporting automatic format and subfolder detection.
  - Implemented multi-view DLT triangulation with RANSAC outlier ray rejection in `src/loom/scaling/aruco.py`:
    - `triangulate_multiview_point()` solves 3D ray intersections via SVD with pair consensus filtering to eliminate rays exceeding `max_reproj_error_px` (> 2.0 px).
    - `ArucoDetector.triangulate_marker_corners()` detects 2D ArUco corners across registered keyframes, undistorts coordinates via camera distortion parameters, and triangulates 4 3D corner coordinates.
    - `ArucoDetector.compute_reconstructed_marker_size()` computes the 4 perimeter Euclidean lengths ($L_{01}, L_{12}, L_{23}, L_{30}$) and derives $L_{\text{sfm}} = \text{median}([L_{01}, L_{12}, L_{23}, L_{30}])$.
  - Integrated metric scale estimation and affine mesh transformation in `src/loom/scaling/processor.py`:
    - Updated `ScalingProcessor.process()` to accept `colmap_dir`, `images_dir`, `frame_paths`, and `max_reprojection_error_px`.
    - Computes metric scale factor $s = \frac{L_{\text{real (mm)}}}{L_{\text{sfm}}}$.
    - Emits structured log: `Metric scaling parameters: Target Marker Size = %.2f mm, Reconstructed SfM Size (L_sfm) = %.6f, Calculated Scale Factor (s) = %.6f`.
    - Applies 4x4 affine transformation matrix ($v' = s \cdot v$) to mesh vertices via `ScaleTransformer.transform_vertices()` and `ScaleTransformer.get_affine_matrix()`.
  - Updated `scripts/demo.py`:
    - Passes `colmap_dir=resolved_sparse` and `images_dir=active_images_dir` to `ScalingProcessor`.
    - Corrected configuration field binding to `marker_size_mm`.
  - Added comprehensive test suite:
    - Added 6 unit tests in `tests/unit/scaling/test_aruco.py` covering COLMAP text parsing, sub-millimeter multi-view triangulation precision, outlier ray rejection, and synthetic scene reconstruction.
    - Added 2 integration tests in `tests/unit/scaling/test_scaling_processor.py` validating end-to-end ArUco triangulation, metric ratio computation, affine matrix vertex scaling, and topology preservation.
- **Verification**:
  - `pytest tests/unit/scaling/`: 37 passed in 0.62s.
  - Entire test suite: 195 passed in 3.83s.
  - `python scripts/demo.py --help`: Verified CLI contracts and flags.
- **Next Steps**:
  - Execute end-to-end pipeline run on real smartphone video with physical ArUco fiducial.

---

## Iteration 022 — Unified Turbo Video-to-3D-Print Pipeline (< 200s Total Runtime Benchmark)
- **Date**: 2026-11-10
- **Milestone**: Phase 1 / Phase 2 / Phase 3 / Phase 4 / Phase 7 / Phase 8 — End-to-End Turbo Pipeline Benchmark Verified
- **Context & Motivation**:
  - Processing hundreds of unconstrained video frames through unoptimized photogrammetry caused 25+ minute bottlenecks, thermal throttling, and memory crashes.
  - Requirement: End-to-end turnaround under 200s (3.5 minutes) from raw smartphone video to a 100% watertight, validated, 2-manifold binary STL.
- **Changes Implemented**:
  - Video Ingest & Downscaling (`src/loom/video/frames.py`, `src/loom/config/models.py`):
    - Added `target_max_dimension: Optional[int] = 960` and `turbo: bool = False` to `VideoConfig`.
    - Downscaled extracted keyframes using `cv2.INTER_AREA` when $\max(H, W) > 960$.
    - In `--turbo` mode, defaulted `max_frames = 36` with even duration striding and Laplacian blur filtering.
  - Live Subprocess Streaming (`src/loom/utils/subprocess.py`):
    - Re-architected `run_subprocess()` with `stream_output=True` using `subprocess.Popen` and daemon pipe reader threads to stream live progress to stdout/stderr while capturing full output.
  - Reconstruction Acceleration (`src/loom/reconstruction/colmap.py`):
    - Added `turbo` flag to `ColmapAdapter.run_matching()`, `run_mapper()`, `run_stereo_fusion()`, and `reconstruct_dense()`.
    - Matching: GPU sequential matching with `overlap=5`, `quadratic_overlap=0`.
    - Mapper: 16 threads, bounded bundle adjustment iterations (`ba_global=12`, `ba_local=10`).
    - Dense MVS: Single-pass photometric stereo (`window_radius=4`, `num_iterations=3`, `geom_consistency=False`, `max_image_size=960`).
    - Meshing: Poisson mesher at depth 9 with `trim=0` directly on `fused.ply` containing native normal vectors.
  - Planar Base Capping with `mapbox-earcut` (`src/loom/mesh/repair.py`):
    - Replaced centroid fan triangulation on base cut loops with `mapbox_earcut.triangulate_float64` (with fallback to pure ear clipping), eliminating self-intersections on non-convex soles.
    - Verified outward downward normal orientation ($n_z < 0$) for all base cap triangles.
  - CLI Turbo Pipeline Integration (`scripts/demo.py`):
    - Added `--turbo` flag auto-configuring `max_frames=36`, `max_image_size=960`, `dense=True`, `align_support=True`, `clean_mesh=True`, `remove_floor=True`, `cap_base=True`, and `base_z=0.005`.
    - Added graceful video path resolution falling back to repository candidates (`data/raw/shoe_2.mp4`).
  - Unit Tests:
    - Added `test_colmap_adapter_turbo_flags` and `test_demo_turbo_cli` in `tests/unit/reconstruction/test_colmap_adapter.py`.
    - Total test suite: 240 passed in 4.55s.
- **Empirical Verification (`outputs/turbo_run`)**:
  - Command: `.venv/bin/python scripts/demo.py --video data/raw/shoe_2.mp4 --output-dir outputs/turbo_run --turbo --target-length 280.0 --export-stl`
  - Total end-to-end turnaround: **151.0 seconds** (2.5 minutes, beating < 200s target).
  - Frame extraction: 36 frames downscaled to $540 \times 960$ in 51.8s.
  - Sparse SfM: SIFT GPU extraction + sequential matching + 16-thread mapper in 7.0s.
  - Dense MVS & Meshing: 88.69s (photometric stereo in 25s, fusion 183k points, Poisson mesher 65,666 verts in 1.6s).
  - Canonical Alignment: RANSAC support plane normal $[0.163, -0.541, -0.825]$ rotated to $[0, 0, 1]^T$ at $Z=0$.
  - Phase 3 Cleaning & Planar Slicing: 5,415 `mapbox-earcut` cap faces across 65 loops at $Z=0.005$.
  - Target Scaling: Uniform scaling ($s=22.78428$) to 280.0 mm in float64 memory.
  - Printability Gate: **PASSED** (watertight=True, 0 boundary edges, 0 non-manifold edges, 0 non-manifold vertices, volume=$448,368.5\,\text{mm}^3$).
  - Binary STL Exported: `outputs/stl/cleaned_aligned_meshed-poisson_metric.stl` (86,850 faces, 4,342,584 bytes).
  - JSON Manifest: `outputs/stl/cleaned_aligned_meshed-poisson_metric_manifest.json`.

---



---

## Iteration 010 — Robust Floor Removal, Centroid Component Isolation, and Planar Base Capping
- **Date**: 2026-11-09
- **Milestone**: Phase 3 — Robust Ground Plane Isolation & 3D Printing Base Preparation
- **Changes Implemented**:
  - Implemented normal-constrained horizontal RANSAC floor detection in `src/loom/mesh/cleanup.py`:
    - `remove_floor_plane()` identifies dominant horizontal planes within normal alignment tolerance (Z-up axis, $|\mathbf{n} \cdot \mathbf{e}_z| \ge \cos(20^\circ)$).
    - Refines plane parameters using PCA/SVD on candidate inliers.
    - Clips floor faces below the bounding box bottom percentile ($Z \le Z_{\min} + 0.15 \Delta Z$) within inlier distance threshold, preventing accidental shearing of legitimate soles.
    - Exports intermediate checkpoint `04_floor_removed.ply` when output path is supplied.
  - Implemented centroid proximity component selection in `src/loom/mesh/cleanup.py` and `src/loom/mesh/components.py`:
    - Added `strategy="centroid_proximity"` in `MeshComponentAnalyzer.filter()` and `MeshCleaner.isolate_target_component()`.
    - Selects the target component closest to spatial reference point (defaulting to bounding box midpoint) rather than naive face count, preventing large background clutter or wall fragments from being erroneously retained over the shoe.
  - Implemented Planar Base Capping in `src/loom/mesh/repair.py`:
    - `slice_and_cap_base()` addresses photogrammetry's inability to view underneath a resting object by slicing geometry at $Z_{\text{base}}$ (or bottom percentile) and cleanly capping the planar boundary loop with downward-facing triangles ($\mathbf{n} = (0, 0, -1)$).
    - Implemented with pure NumPy planar triangle clipping and 2D ear-clipping hole closure, completely avoiding external `shapely` dependencies (ADR-011).
    - Guarantees a flat contact surface for 3D printer build plate adhesion and watertight geometry.
    - Exports intermediate checkpoint `05_base_capped.ply` when output path is supplied.
  - Integrated into Phase 3 orchestrator `src/loom/mesh/processor.py`:
    - Added `floor_removal_enabled` and `base_capping_enabled` stages in `MeshProcessor.process()`.
    - Updated `MeshProcessingStage` enum and `MeshProcessingResult` with floor and base capping action metadata.
  - Updated `scripts/demo.py`:
    - Added CLI flags: `--remove-floor`, `--cap-base`, and `--component-strategy {centroid_proximity,largest,largest_by_area,min_faces,keep_all}`.
    - Preserves intermediate checkpoints `04_floor_removed.ply` and `05_base_capped.ply` in `outputs/reconstructions/<run_name>/`.
  - Added comprehensive test suite:
    - Added 3 unit tests in `tests/unit/mesh/test_cleanup.py` covering synthetic horizontal floor plane RANSAC clipping, centroid proximity selection over distant clutter, and component analyzer configuration.
    - Added 3 unit tests in `tests/unit/mesh/test_repair.py` covering closed box slicing/capping, open-bottom cylinder healing, and percentile-based slicing.
- **Verification**:
  - `pytest tests/unit/mesh/test_cleanup.py tests/unit/mesh/test_repair.py`: 15 passed in 0.38s.
  - Full mesh and pipeline test suites: 92 passed in 0.64s.
  - `python scripts/demo.py --help`: Verified CLI contracts and flags.
- **Next Steps**:
  - Execute end-to-end photogrammetry and printability verification on real capture data.
- **Date**: 2026-11-09
- **Milestone**: Phase 2 / Phase 3 — Reconstruction Artifact Preservations & Point Cloud Pre-Repair Diagnostics
- **Changes Implemented**:
  - Implemented intermediate artifact checkpoints in `src/loom/pipeline/artifacts.py`:
    - Created typed data model `ReconstructionCheckpointsArtifact` preserving paths, point counts, spatial density, and coverage flags.
    - Added helper `read_ply_vertex_count()` reading vertex elements directly from ASCII and binary PLY headers in microsecond time without external dependencies.
    - Added `compute_ply_density()` estimating spatial bounding box volume $V$ and density (points/unit³).
    - Added `export_sparse_points_ply()` converting/copying sparse feature points (`points3D.bin`, `points3D.txt`, or direct PLY) into standard `points3D.ply`.
    - Implemented `export_reconstruction_checkpoints()` preserving intermediate artifacts to disk hierarchy:
      - `outputs/reconstructions/<run_name>/01_sparse/points3D.ply` (sparse feature points)
      - `outputs/reconstructions/<run_name>/02_dense/fused.ply` (dense fused point cloud)
      - `outputs/reconstructions/<run_name>/03_raw_mesh/meshed-poisson.ply` (untrimmed Poisson mesh)
  - Integrated diagnostic checks after stereo fusion:
    - Added vertex count check to `fused.ply` in both `ColmapAdapter.reconstruct_dense()` and `export_reconstruction_checkpoints()`.
    - Logs total points and spatial density.
    - If points < 50,000 threshold, emits high-severity warning: `HIGH SEVERITY WARNING: Fused point cloud has insufficient points (< 50,000 threshold). Parallax or coverage was insufficient during capture, risking incomplete surface reconstruction.`
  - Updated `src/loom/pipeline/runner.py`:
    - Added `run_phase2_reconstruction_pipeline()` enabling standalone Phase 2 execution with automatic intermediate checkpoint export.
    - Updated `run_phase1_pipeline()` to preserve checkpoints and serialize diagnostic metadata in `reconstruction.json`.
    - Decoupled optional module-level imports via `TYPE_CHECKING` across pipeline stages.
  - Updated `scripts/demo.py` to preserve intermediate checkpoints after reconstruction.
  - Authored test suite in `tests/unit/pipeline/test_artifacts.py` covering header parsing, density computation, checkpoint exports, and diagnostic warning assertions.
- **Verification**:
  - `pytest tests/unit/pipeline/test_artifacts.py`: 11 passed in 0.05s.
  - `pytest tests/unit/reconstruction/test_colmap_adapter.py`: 15 passed in 0.06s.
  - `python scripts/demo.py --help`: Verified operational.
  - Verified disk structure conforms to `outputs/reconstructions/<run_name>/{01_sparse,02_dense,03_raw_mesh}/`.
- **Next Steps**:
  - Execute live capture validation with shoe dataset and ArUco fiducial.

---

## Iteration 022 — Unified Turbo Video-to-3D-Print Pipeline (< 200s Total Runtime Benchmark)
- **Date**: 2026-11-10
- **Milestone**: Phase 1 / Phase 2 / Phase 3 / Phase 4 / Phase 7 / Phase 8 — End-to-End Turbo Pipeline Benchmark Verified
- **Context & Motivation**:
  - Processing hundreds of unconstrained video frames through unoptimized photogrammetry caused 25+ minute bottlenecks, thermal throttling, and memory crashes.
  - Requirement: End-to-end turnaround under 200s (3.5 minutes) from raw smartphone video to a 100% watertight, validated, 2-manifold binary STL.
- **Changes Implemented**:
  - Video Ingest & Downscaling (`src/loom/video/frames.py`, `src/loom/config/models.py`):
    - Added `target_max_dimension: Optional[int] = 960` and `turbo: bool = False` to `VideoConfig`.
    - Downscaled extracted keyframes using `cv2.INTER_AREA` when $\max(H, W) > 960$.
    - In `--turbo` mode, defaulted `max_frames = 36` with even duration striding and Laplacian blur filtering.
  - Live Subprocess Streaming (`src/loom/utils/subprocess.py`):
    - Re-architected `run_subprocess()` with `stream_output=True` using `subprocess.Popen` and daemon pipe reader threads to stream live progress to stdout/stderr while capturing full output.
  - Reconstruction Acceleration (`src/loom/reconstruction/colmap.py`):
    - Added `turbo` flag to `ColmapAdapter.run_matching()`, `run_mapper()`, `run_stereo_fusion()`, and `reconstruct_dense()`.
    - Matching: GPU sequential matching with `overlap=5`, `quadratic_overlap=0`.
    - Mapper: 16 threads, bounded bundle adjustment iterations (`ba_global=12`, `ba_local=10`).
    - Dense MVS: Single-pass photometric stereo (`window_radius=4`, `num_iterations=3`, `geom_consistency=False`, `max_image_size=960`).
    - Meshing: Poisson mesher at depth 9 with `trim=0` directly on `fused.ply` containing native normal vectors.
  - Planar Base Capping with `mapbox-earcut` (`src/loom/mesh/repair.py`):
    - Replaced centroid fan triangulation on base cut loops with `mapbox_earcut.triangulate_float64` (with fallback to pure ear clipping), eliminating self-intersections on non-convex soles.
    - Verified outward downward normal orientation ($n_z < 0$) for all base cap triangles.
  - CLI Turbo Pipeline Integration (`scripts/demo.py`):
    - Added `--turbo` flag auto-configuring `max_frames=36`, `max_image_size=960`, `dense=True`, `align_support=True`, `clean_mesh=True`, `remove_floor=True`, `cap_base=True`, and `base_z=0.005`.
    - Added graceful video path resolution falling back to repository candidates (`data/raw/shoe_2.mp4`).
  - Unit Tests:
    - Added `test_colmap_adapter_turbo_flags` and `test_demo_turbo_cli` in `tests/unit/reconstruction/test_colmap_adapter.py`.
    - Total test suite: 240 passed in 4.55s.
- **Empirical Verification (`outputs/turbo_run`)**:
  - Command: `.venv/bin/python scripts/demo.py --video data/raw/shoe_2.mp4 --output-dir outputs/turbo_run --turbo --target-length 280.0 --export-stl`
  - Total end-to-end turnaround: **151.0 seconds** (2.5 minutes, beating < 200s target).
  - Frame extraction: 36 frames downscaled to $540 \times 960$ in 51.8s.
  - Sparse SfM: SIFT GPU extraction + sequential matching + 16-thread mapper in 7.0s.
  - Dense MVS & Meshing: 88.69s (photometric stereo in 25s, fusion 183k points, Poisson mesher 65,666 verts in 1.6s).
  - Canonical Alignment: RANSAC support plane normal $[0.163, -0.541, -0.825]$ rotated to $[0, 0, 1]^T$ at $Z=0$.
  - Phase 3 Cleaning & Planar Slicing: 5,415 `mapbox-earcut` cap faces across 65 loops at $Z=0.005$.
  - Target Scaling: Uniform scaling ($s=22.78428$) to 280.0 mm in float64 memory.
  - Printability Gate: **PASSED** (watertight=True, 0 boundary edges, 0 non-manifold edges, 0 non-manifold vertices, volume=$448,368.5\,\text{mm}^3$).
  - Binary STL Exported: `outputs/stl/cleaned_aligned_meshed-poisson_metric.stl` (86,850 faces, 4,342,584 bytes).
  - JSON Manifest: `outputs/stl/cleaned_aligned_meshed-poisson_metric_manifest.json`.

---



---

## Iteration 008 — ColmapAdapter Dense Stereo CUDA Pipeline & scripts/demo.py Unification
- **Date**: 2026-11-09
- **Milestone**: Phase 2 — Reconstruction Backend Integration (COLMAP Dense CUDA Stereo & Demo Unification)
- **Changes Implemented**:
  - Implemented production `ColmapAdapter` in `src/loom/reconstruction/colmap.py`:
    - Dense stereo argument builders for `patch_match_stereo` enforcing hardware safety and CUDA stereo flags:
      `--PatchMatchStereo.gpu_index 0`
      `--PatchMatchStereo.max_image_size 1600` (protects 8 GB VRAM buffer)
      `--PatchMatchStereo.window_radius 5`
      `--PatchMatchStereo.num_iterations 5`
      `--PatchMatchStereo.geom_consistency true`
    - Implemented sequential dense MVS pipeline `reconstruct_dense()`:
      `image_undistorter` -> `patch_match_stereo` -> `stereo_fusion` -> `poisson_mesher`
    - Added typed artifacts `ColmapDenseArtifact` and `ColmapSparseArtifact` (subclassing `ReconstructionArtifact`), with `artifact.mesh_path` and `artifact.poisson_mesh_path` pointing directly to the generated `meshed-poisson.ply`.
    - Implemented `reconstruct_sparse_mesh()` executing `colmap delaunay_mesher --input_type sparse` as an explicit diagnostic preview.
    - Implemented full `ReconstructionEngine.reconstruct()` interface with feature extraction, matching, and mapper orchestration.
  - Implemented unified CLI & workflow runner in `scripts/demo.py`:
    - Removed disconnected subprocess calls for sparse Delaunay meshing.
    - Refactored reconstruction execution to invoke `ColmapAdapter` directly from `src/loom/reconstruction/colmap.py`.
    - If `--dense` is flagged: executes `adapter.reconstruct_dense()`. Strictly avoids silent fallback to sparse Delaunay if dense fails, raising clear `ReconstructionError`.
    - If `--dense` is omitted: requires `--allow-sparse-fallback` to run sparse meshing as an explicitly labeled diagnostic preview, raising `ReconstructionError` if omitted.
    - Maintained modular downstream handoffs to Phase 3 mesh repair and Phase 4 metric scaling without altering their core logic.
  - Resolved eager import chain in `src/loom/pipeline/__init__.py` using PEP 562 module `__getattr__` for `runner` and `stages`, decoupling typed artifact consumers from optional imaging libraries.
  - Authored comprehensive test suite in `tests/unit/reconstruction/test_colmap_adapter.py`:
    - 15 unit tests verifying binary resolution, CUDA argument construction, 4-stage sequential pipeline execution, typed artifact validation, error propagation, sparse Delaunay diagnostic previews, and `scripts/demo.py` workflow contracts.
- **Verification**:
  - `pytest tests/unit/reconstruction/test_colmap_adapter.py`: 15 passed in 0.05s.
  - `python scripts/demo.py --help`: Verified CLI contracts and flags (`--dense`, `--allow-sparse-fallback`, `--gpu-index`, `--max-image-size`).
  - Total 41 unit tests passing across reconstruction, core configuration, and pipeline artifacts.
- **Next Steps**:
  - Execute end-to-end live photogrammetry run on captured smartphone frames using `/usr/bin/colmap`.

---

## Iteration 022 — Unified Turbo Video-to-3D-Print Pipeline (< 200s Total Runtime Benchmark)
- **Date**: 2026-11-10
- **Milestone**: Phase 1 / Phase 2 / Phase 3 / Phase 4 / Phase 7 / Phase 8 — End-to-End Turbo Pipeline Benchmark Verified
- **Context & Motivation**:
  - Processing hundreds of unconstrained video frames through unoptimized photogrammetry caused 25+ minute bottlenecks, thermal throttling, and memory crashes.
  - Requirement: End-to-end turnaround under 200s (3.5 minutes) from raw smartphone video to a 100% watertight, validated, 2-manifold binary STL.
- **Changes Implemented**:
  - Video Ingest & Downscaling (`src/loom/video/frames.py`, `src/loom/config/models.py`):
    - Added `target_max_dimension: Optional[int] = 960` and `turbo: bool = False` to `VideoConfig`.
    - Downscaled extracted keyframes using `cv2.INTER_AREA` when $\max(H, W) > 960$.
    - In `--turbo` mode, defaulted `max_frames = 36` with even duration striding and Laplacian blur filtering.
  - Live Subprocess Streaming (`src/loom/utils/subprocess.py`):
    - Re-architected `run_subprocess()` with `stream_output=True` using `subprocess.Popen` and daemon pipe reader threads to stream live progress to stdout/stderr while capturing full output.
  - Reconstruction Acceleration (`src/loom/reconstruction/colmap.py`):
    - Added `turbo` flag to `ColmapAdapter.run_matching()`, `run_mapper()`, `run_stereo_fusion()`, and `reconstruct_dense()`.
    - Matching: GPU sequential matching with `overlap=5`, `quadratic_overlap=0`.
    - Mapper: 16 threads, bounded bundle adjustment iterations (`ba_global=12`, `ba_local=10`).
    - Dense MVS: Single-pass photometric stereo (`window_radius=4`, `num_iterations=3`, `geom_consistency=False`, `max_image_size=960`).
    - Meshing: Poisson mesher at depth 9 with `trim=0` directly on `fused.ply` containing native normal vectors.
  - Planar Base Capping with `mapbox-earcut` (`src/loom/mesh/repair.py`):
    - Replaced centroid fan triangulation on base cut loops with `mapbox_earcut.triangulate_float64` (with fallback to pure ear clipping), eliminating self-intersections on non-convex soles.
    - Verified outward downward normal orientation ($n_z < 0$) for all base cap triangles.
  - CLI Turbo Pipeline Integration (`scripts/demo.py`):
    - Added `--turbo` flag auto-configuring `max_frames=36`, `max_image_size=960`, `dense=True`, `align_support=True`, `clean_mesh=True`, `remove_floor=True`, `cap_base=True`, and `base_z=0.005`.
    - Added graceful video path resolution falling back to repository candidates (`data/raw/shoe_2.mp4`).
  - Unit Tests:
    - Added `test_colmap_adapter_turbo_flags` and `test_demo_turbo_cli` in `tests/unit/reconstruction/test_colmap_adapter.py`.
    - Total test suite: 240 passed in 4.55s.
- **Empirical Verification (`outputs/turbo_run`)**:
  - Command: `.venv/bin/python scripts/demo.py --video data/raw/shoe_2.mp4 --output-dir outputs/turbo_run --turbo --target-length 280.0 --export-stl`
  - Total end-to-end turnaround: **151.0 seconds** (2.5 minutes, beating < 200s target).
  - Frame extraction: 36 frames downscaled to $540 \times 960$ in 51.8s.
  - Sparse SfM: SIFT GPU extraction + sequential matching + 16-thread mapper in 7.0s.
  - Dense MVS & Meshing: 88.69s (photometric stereo in 25s, fusion 183k points, Poisson mesher 65,666 verts in 1.6s).
  - Canonical Alignment: RANSAC support plane normal $[0.163, -0.541, -0.825]$ rotated to $[0, 0, 1]^T$ at $Z=0$.
  - Phase 3 Cleaning & Planar Slicing: 5,415 `mapbox-earcut` cap faces across 65 loops at $Z=0.005$.
  - Target Scaling: Uniform scaling ($s=22.78428$) to 280.0 mm in float64 memory.
  - Printability Gate: **PASSED** (watertight=True, 0 boundary edges, 0 non-manifold edges, 0 non-manifold vertices, volume=$448,368.5\,\text{mm}^3$).
  - Binary STL Exported: `outputs/stl/cleaned_aligned_meshed-poisson_metric.stl` (86,850 faces, 4,342,584 bytes).
  - JSON Manifest: `outputs/stl/cleaned_aligned_meshed-poisson_metric_manifest.json`.

---



---

## Iteration 007 — Phase 4: Metric Scaling Subsystem Implementation & Synthetic Validation
- **Date**: 2026-10-01
- **Milestone**: Phase 4 — Metric Scaling (IMPLEMENTED & SYNTHETICALLY VERIFIED with 155 total tests; Physical Validation Pending Live Capture with ArUco Fiducial)
- **Changes Implemented**:
  - Audited OpenCV dependency: confirmed `opencv-python==5.0.0.93` provides full native `cv2.aruco` support (`ArucoDetector`, `DetectorParameters`, predefined dictionaries). Zero new dependencies added.
  - Implemented typed domain exceptions in `src/loom/scaling/exceptions.py`: `ScalingError`, `ScalingConfigError`, `ReferenceDetectionError`, `ReferenceMeasurementError`, `ScaleEstimationError`, `MeshScalingError`, `MeshScalingValidationError`.
  - Implemented typed data models in `src/loom/scaling/models.py`: `ReferenceMarker`, `MarkerObservation`, `ReferenceMeasurement`, `ScaleEstimate`, and `ScalingResult` with complete JSON serialization.
  - Implemented ArUco detector in `src/loom/scaling/aruco.py`: dictionary lookup (`DICT_4X4_50`, etc.), 2D corner extraction, target ID filtering, and synthetic marker generation.
  - Implemented measurement & scale estimation engine in `src/loom/scaling/measurement.py`: `MeasurementEngine` (multi-observation distance aggregation, 3D perimeter calculation, rejection of invalid/non-finite measurements) and `ScaleEstimator` ($s = d_{\text{phys}} / d_{\text{recon}}$ with variance and confidence).
  - Implemented deterministic mesh transformer in `src/loom/scaling/transform.py`: `ScaleTransformer` applying vertex scaling $\mathbf{p}_{\text{scaled}} = \mathbf{p}_{\text{orig}} + s \cdot (\mathbf{p} - \mathbf{p}_{\text{orig}})$ about an explicit origin while keeping vertex count, face count, and topology 100% invariant.
  - Implemented scaling orchestrator in `src/loom/scaling/processor.py`: `ScalingProcessor` handling input mesh validation, reference measurement, scale estimation, transformation, output validation, and JSON report generation.
  - Updated configuration models in `src/loom/config/models.py` and `src/loom/config/loader.py`: `ScalingConfig` supporting flat keys and nested YAML syntax with backwards compatibility.
  - Added standalone pipeline runner in `src/loom/pipeline/runner.py`: `run_phase4_scaling_pipeline()` generating `scaled_<stem>.obj` and `reports/scaling.json`.
  - Added dedicated CLI subcommand in `src/loom/__main__.py`: `loom scale --input <mesh> --reference-size <mm> --measured-size <units>` with structured terminal summary.
  - Authored comprehensive specification in `docs/scaling.md`.
  - Added 31 unit and integration tests across `tests/unit/scaling/` and `tests/integration/scaling_pipeline/`.
- **Verification**:
  - Full test suite passed: **155 passed in 7.32s** (100% pass rate, 31 new tests + 124 existing tests, zero regressions, zero warnings).
  - CLI execution verified: `python -m loom scale --input data/raw/sample_photogrammetry_raw.obj --reference-size 50.0 --measured-size 25.0` completed in 0.0055s, producing exact $2.0\times$ scaled mesh and `reports/scaling.json`.
  - Synthetic box ($25\text{ mm} \to 50\text{ mm}$) verified with $0.000\%$ relative error and zero topology distortion.
- **Next Steps**:
  - Provision external reconstruction tool (`meshroom_batch` or `colmap`) to unblock live photogrammetry (`ISSUE-BLK-002`).
  - Execute live smartphone video capture with physical ArUco fiducial to perform physical ground truth accuracy validation.
  - Proceed to Phase 5 (Geometry & Ground-Truth Dimensional Validation).

---

## Iteration 022 — Unified Turbo Video-to-3D-Print Pipeline (< 200s Total Runtime Benchmark)
- **Date**: 2026-11-10
- **Milestone**: Phase 1 / Phase 2 / Phase 3 / Phase 4 / Phase 7 / Phase 8 — End-to-End Turbo Pipeline Benchmark Verified
- **Context & Motivation**:
  - Processing hundreds of unconstrained video frames through unoptimized photogrammetry caused 25+ minute bottlenecks, thermal throttling, and memory crashes.
  - Requirement: End-to-end turnaround under 200s (3.5 minutes) from raw smartphone video to a 100% watertight, validated, 2-manifold binary STL.
- **Changes Implemented**:
  - Video Ingest & Downscaling (`src/loom/video/frames.py`, `src/loom/config/models.py`):
    - Added `target_max_dimension: Optional[int] = 960` and `turbo: bool = False` to `VideoConfig`.
    - Downscaled extracted keyframes using `cv2.INTER_AREA` when $\max(H, W) > 960$.
    - In `--turbo` mode, defaulted `max_frames = 36` with even duration striding and Laplacian blur filtering.
  - Live Subprocess Streaming (`src/loom/utils/subprocess.py`):
    - Re-architected `run_subprocess()` with `stream_output=True` using `subprocess.Popen` and daemon pipe reader threads to stream live progress to stdout/stderr while capturing full output.
  - Reconstruction Acceleration (`src/loom/reconstruction/colmap.py`):
    - Added `turbo` flag to `ColmapAdapter.run_matching()`, `run_mapper()`, `run_stereo_fusion()`, and `reconstruct_dense()`.
    - Matching: GPU sequential matching with `overlap=5`, `quadratic_overlap=0`.
    - Mapper: 16 threads, bounded bundle adjustment iterations (`ba_global=12`, `ba_local=10`).
    - Dense MVS: Single-pass photometric stereo (`window_radius=4`, `num_iterations=3`, `geom_consistency=False`, `max_image_size=960`).
    - Meshing: Poisson mesher at depth 9 with `trim=0` directly on `fused.ply` containing native normal vectors.
  - Planar Base Capping with `mapbox-earcut` (`src/loom/mesh/repair.py`):
    - Replaced centroid fan triangulation on base cut loops with `mapbox_earcut.triangulate_float64` (with fallback to pure ear clipping), eliminating self-intersections on non-convex soles.
    - Verified outward downward normal orientation ($n_z < 0$) for all base cap triangles.
  - CLI Turbo Pipeline Integration (`scripts/demo.py`):
    - Added `--turbo` flag auto-configuring `max_frames=36`, `max_image_size=960`, `dense=True`, `align_support=True`, `clean_mesh=True`, `remove_floor=True`, `cap_base=True`, and `base_z=0.005`.
    - Added graceful video path resolution falling back to repository candidates (`data/raw/shoe_2.mp4`).
  - Unit Tests:
    - Added `test_colmap_adapter_turbo_flags` and `test_demo_turbo_cli` in `tests/unit/reconstruction/test_colmap_adapter.py`.
    - Total test suite: 240 passed in 4.55s.
- **Empirical Verification (`outputs/turbo_run`)**:
  - Command: `.venv/bin/python scripts/demo.py --video data/raw/shoe_2.mp4 --output-dir outputs/turbo_run --turbo --target-length 280.0 --export-stl`
  - Total end-to-end turnaround: **151.0 seconds** (2.5 minutes, beating < 200s target).
  - Frame extraction: 36 frames downscaled to $540 \times 960$ in 51.8s.
  - Sparse SfM: SIFT GPU extraction + sequential matching + 16-thread mapper in 7.0s.
  - Dense MVS & Meshing: 88.69s (photometric stereo in 25s, fusion 183k points, Poisson mesher 65,666 verts in 1.6s).
  - Canonical Alignment: RANSAC support plane normal $[0.163, -0.541, -0.825]$ rotated to $[0, 0, 1]^T$ at $Z=0$.
  - Phase 3 Cleaning & Planar Slicing: 5,415 `mapbox-earcut` cap faces across 65 loops at $Z=0.005$.
  - Target Scaling: Uniform scaling ($s=22.78428$) to 280.0 mm in float64 memory.
  - Printability Gate: **PASSED** (watertight=True, 0 boundary edges, 0 non-manifold edges, 0 non-manifold vertices, volume=$448,368.5\,\text{mm}^3$).
  - Binary STL Exported: `outputs/stl/cleaned_aligned_meshed-poisson_metric.stl` (86,850 faces, 4,342,584 bytes).
  - JSON Manifest: `outputs/stl/cleaned_aligned_meshed-poisson_metric_manifest.json`.

---



---

## Iteration 006 — Phase 2 & Phase 3 Validation, Hardening & Pipeline Handoff Audit
- **Date**: 2026-10-01
- **Milestone**: Phase 2 — Reconstruction Backend Integration (Adapter & Contracts Verified; Host Binary BLOCKED `ISSUE-BLK-002`); Phase 3 — Raw Geometry & Mesh Processing (VERIFIED & AUDITED with 124 total tests)
- **Changes Implemented**:
  - Audited host environment photogrammetry executables: searched system PATH, `C:\`, `C:\Program Files`, `C:\Users\adise`, `AppData`, `tools`. Neither `meshroom_batch.exe` nor `colmap.exe` is present on disk (`ISSUE-BLK-002`). Confirmed NVIDIA GeForce RTX 4060 Laptop GPU with Driver 592.82 and CUDA 13.1 ready for photogrammetry binary installation.
  - Phase 2 live reconstruction status kept explicitly marked `BLOCKED` as mandated by project constitution and completion gates.
  - Hardened `MeshroomAdapter` in `src/loom/reconstruction/meshroom.py`:
    - Updated `parse_camera_sfm` to handle both dictionary and list JSON schemas for `views` and `poses`, calculate pose counts, clamp `registration_ratio` to $[0.0, 1.0]$.
    - Added `.stl` candidate extension to mesh discovery, added fallback to `sfm.json` if `cameras.sfm` is absent.
  - Hardened Phase 3 geometry diagnostics and cleanup:
    - Added configurable `degenerate_area_threshold: float = 1e-7` to `MeshConfig` in `src/loom/config/models.py`.
    - Updated `MeshDiagnostics.inspect()` and `MeshCleaner.clean()` to detect and purge collinear sliver triangles while accounting for float serialization rounding differences between memory and disk representations.
    - Suppressed Trimesh internal `RuntimeWarning: invalid value encountered in divide` on open surfaces by guarding `fix_inversion` with `if mesh.is_watertight:` and `warnings.catch_warnings()`.
  - Hardened pipeline orchestration in `src/loom/pipeline/runner.py`:
    - Added safety try/except wrapper around `MeshProcessor.process` in `run_phase1_pipeline`. When a raw mesh is corrupt or unreadable, sets `mesh_processing_result.status = "FAILED"`, writes `geometry.json`, and cleanly separates reconstruction success from geometry processing failure.
    - Added user warning when `--clean-mesh` is requested with video input without `--reconstruct`.
  - Added photogrammetry raw mesh fixture in `tests/fixtures/mesh_fixtures.py` (`create_photogrammetry_raw_mesh`):
    - Synthesized 1040-triangle sphere dome with 40-edge open base boundary, 3-edge pinhole, 2 floating satellite noise clusters, collinear slivers, duplicate faces, unreferenced vertices, and arbitrary SfM offset coordinates.
    - Saved reference raw mesh fixture to `data/raw/sample_photogrammetry_raw.obj`.
  - Added comprehensive test suites (9 new tests):
    - `tests/unit/mesh/test_photogrammetry_audit.py` (6 unit audit tests verifying diagnostics, component selection, cleanup, conservative hole repair, scale/coordinate preservation, and JSON report generation on realistic photogrammetry mesh).
    - `tests/integration/full_pipeline/test_phase2_phase3_handoff.py` (3 integration tests verifying full Phase 1 $\to$ Phase 2 $\to$ Phase 3 handoff, reconstruction failure skipping Phase 3, and failure discrimination between reconstruction success and corrupt mesh processing failure).
- **Verification**:
  - Full test suite passed: **124 passed in 9.28s** (100% pass rate, 9 new tests + 115 existing tests, zero failures, zero warnings).
  - CLI execution verified: `python -m loom geometry --input data/raw/sample_photogrammetry_raw.obj` executed in 0.0508s, producing `cleaned_sample_photogrammetry_raw.obj` and `reports/geometry.json`.
  - Degraded execution verified: `python -m loom --video data/raw/synthetic_test.mp4 --reconstruct --clean-mesh` completed cleanly with `Status: RECONSTRUCTION BLOCKED (Backend Executable Unavailable on Host)`.
- **Next Step**:
  - Provision external reconstruction tool (`meshroom_batch` or `colmap`) to unblock live photogrammetry (`ISSUE-BLK-002`).
  - Proceed with Phase 4 (Fiducial Metric Scaling & Coordinate Transformation).

---

## Iteration 022 — Unified Turbo Video-to-3D-Print Pipeline (< 200s Total Runtime Benchmark)
- **Date**: 2026-11-10
- **Milestone**: Phase 1 / Phase 2 / Phase 3 / Phase 4 / Phase 7 / Phase 8 — End-to-End Turbo Pipeline Benchmark Verified
- **Context & Motivation**:
  - Processing hundreds of unconstrained video frames through unoptimized photogrammetry caused 25+ minute bottlenecks, thermal throttling, and memory crashes.
  - Requirement: End-to-end turnaround under 200s (3.5 minutes) from raw smartphone video to a 100% watertight, validated, 2-manifold binary STL.
- **Changes Implemented**:
  - Video Ingest & Downscaling (`src/loom/video/frames.py`, `src/loom/config/models.py`):
    - Added `target_max_dimension: Optional[int] = 960` and `turbo: bool = False` to `VideoConfig`.
    - Downscaled extracted keyframes using `cv2.INTER_AREA` when $\max(H, W) > 960$.
    - In `--turbo` mode, defaulted `max_frames = 36` with even duration striding and Laplacian blur filtering.
  - Live Subprocess Streaming (`src/loom/utils/subprocess.py`):
    - Re-architected `run_subprocess()` with `stream_output=True` using `subprocess.Popen` and daemon pipe reader threads to stream live progress to stdout/stderr while capturing full output.
  - Reconstruction Acceleration (`src/loom/reconstruction/colmap.py`):
    - Added `turbo` flag to `ColmapAdapter.run_matching()`, `run_mapper()`, `run_stereo_fusion()`, and `reconstruct_dense()`.
    - Matching: GPU sequential matching with `overlap=5`, `quadratic_overlap=0`.
    - Mapper: 16 threads, bounded bundle adjustment iterations (`ba_global=12`, `ba_local=10`).
    - Dense MVS: Single-pass photometric stereo (`window_radius=4`, `num_iterations=3`, `geom_consistency=False`, `max_image_size=960`).
    - Meshing: Poisson mesher at depth 9 with `trim=0` directly on `fused.ply` containing native normal vectors.
  - Planar Base Capping with `mapbox-earcut` (`src/loom/mesh/repair.py`):
    - Replaced centroid fan triangulation on base cut loops with `mapbox_earcut.triangulate_float64` (with fallback to pure ear clipping), eliminating self-intersections on non-convex soles.
    - Verified outward downward normal orientation ($n_z < 0$) for all base cap triangles.
  - CLI Turbo Pipeline Integration (`scripts/demo.py`):
    - Added `--turbo` flag auto-configuring `max_frames=36`, `max_image_size=960`, `dense=True`, `align_support=True`, `clean_mesh=True`, `remove_floor=True`, `cap_base=True`, and `base_z=0.005`.
    - Added graceful video path resolution falling back to repository candidates (`data/raw/shoe_2.mp4`).
  - Unit Tests:
    - Added `test_colmap_adapter_turbo_flags` and `test_demo_turbo_cli` in `tests/unit/reconstruction/test_colmap_adapter.py`.
    - Total test suite: 240 passed in 4.55s.
- **Empirical Verification (`outputs/turbo_run`)**:
  - Command: `.venv/bin/python scripts/demo.py --video data/raw/shoe_2.mp4 --output-dir outputs/turbo_run --turbo --target-length 280.0 --export-stl`
  - Total end-to-end turnaround: **151.0 seconds** (2.5 minutes, beating < 200s target).
  - Frame extraction: 36 frames downscaled to $540 \times 960$ in 51.8s.
  - Sparse SfM: SIFT GPU extraction + sequential matching + 16-thread mapper in 7.0s.
  - Dense MVS & Meshing: 88.69s (photometric stereo in 25s, fusion 183k points, Poisson mesher 65,666 verts in 1.6s).
  - Canonical Alignment: RANSAC support plane normal $[0.163, -0.541, -0.825]$ rotated to $[0, 0, 1]^T$ at $Z=0$.
  - Phase 3 Cleaning & Planar Slicing: 5,415 `mapbox-earcut` cap faces across 65 loops at $Z=0.005$.
  - Target Scaling: Uniform scaling ($s=22.78428$) to 280.0 mm in float64 memory.
  - Printability Gate: **PASSED** (watertight=True, 0 boundary edges, 0 non-manifold edges, 0 non-manifold vertices, volume=$448,368.5\,\text{mm}^3$).
  - Binary STL Exported: `outputs/stl/cleaned_aligned_meshed-poisson_metric.stl` (86,850 faces, 4,342,584 bytes).
  - JSON Manifest: `outputs/stl/cleaned_aligned_meshed-poisson_metric_manifest.json`.

---



---

## Iteration 005 — Phase 3: Raw Geometry & Mesh Processing Implementation & Fixture Validation
- **Date**: 2026-10-01
- **Milestone**: Phase 3 — Raw Geometry & Mesh Processing (IMPLEMENTED & FIXTURE-TESTED with 115 tests; Live Reconstruction: Awaiting Host Binary `ISSUE-BLK-002`)
- **Changes Implemented**:
  - Enforced strict Phase 3 architectural boundaries: zero Phase 4+ functionality added (no metric scaling, no ArUco markers, no absolute dimensions, no CAD ground-truth accuracy benchmarking, no printability analysis, no STL manufacturing export, no neural AI/PyTorch/Depth Anything dependencies). Reconstructed coordinates and physical scale strictly preserved.
  - Installed authorized dependencies: `trimesh==5.1.0` and `scipy==1.15.3` (authorized under `.agents/rules/python.md`). Updated `pyproject.toml`.
  - Implemented typed domain exceptions in `src/loom/mesh/exceptions.py`: `MeshError`, `MeshFormatError`, `MeshInvalidError`, `MeshLoadError`, `MeshProcessingError`.
  - Extended configuration models in `src/loom/config/models.py`: added `component_strategy`, `min_component_faces`, `min_component_ratio`, `remove_degenerate_faces`, `remove_unreferenced_vertices`, `remove_duplicate_faces`, `unify_normals`, `max_hole_edges`, `fill_holes`.
  - Implemented typed data models in `src/loom/mesh/models.py`: `GeometryDiagnostics`, `ComponentInfo`, `ComponentActionResult`, `CleanupActionResult`, `RepairActionResult`, `MeshProcessingResult`, and `MeshProcessingStage` enum.
  - Implemented read-only diagnostics in `src/loom/mesh/diagnostics.py`: vertex/face counts, bounding box, extents, volume, surface area, component count, boundary edges, boundary loops, non-manifold edges/vertices, watertightness, Euler characteristic, NaN/Inf detection, zero-area degenerate triangles, duplicate faces, unreferenced vertices, and status categorization (`VALID`, `WARNING`, `ERROR`).
  - Implemented connected component analysis in `src/loom/mesh/components.py`: `MeshComponentAnalyzer` supporting strategies (`largest`, `largest_by_area`, `min_faces`, `relative_threshold`, `keep_all`) based on face-adjacency graph traversal without external graph packages.
  - Implemented deterministic cleanup in `src/loom/mesh/cleanup.py`: `MeshCleaner` removing NaN/Inf vertices, invalid face indices, zero-area degenerate triangles (cross-product area $\le 10^{-12}$), duplicate faces, and unreferenced vertices.
  - Implemented conservative hole repair in `src/loom/mesh/repair.py`: `MeshRepairer` extracting directed boundary loops, classifying defects by size threshold (`max_hole_edges`), triangulating eligible loops via 2D ear-clipping, honestly preserving complex defects in `defect_details`, and unifiying outward normals via pure NumPy BFS without `networkx`.
  - Implemented pipeline orchestrator in `src/loom/mesh/processor.py`: `MeshProcessor` managing the 8-stage pipeline while strictly preserving coordinate values and physical scale.
  - Implemented standalone runner in `src/loom/pipeline/runner.py`: `run_phase3_mesh_pipeline()` generating `outputs/runs/<run_id>/geometry/cleaned_<stem>.obj` and `reports/geometry.json`.
  - Integrated Phase 3 into CLI (`src/loom/__main__.py`): added `geometry` subcommand (`python -m loom geometry --input <mesh>`) and direct flag (`--mesh`), with structured terminal diagnostic summary.
  - Authored comprehensive Phase 3 specification in `docs/geometry.md`.
  - Constructed deterministic test fixtures in `tests/fixtures/mesh_fixtures.py` (`clean_cube`, `disconnected_mesh`, `degenerate_mesh`, `hole_mesh`, `large_hole_mesh`, `duplicate_and_unreferenced_mesh`).
  - Added 40 new unit and integration tests across `tests/unit/mesh/` and `tests/integration/mesh_pipeline/`.
- **Verification**:
  - Full test suite passed: **115 passed in 7.20s** (100% pass rate, 40 new tests + 75 existing tests, zero regressions).
  - Validated all 4 core fixture types through end-to-end pipeline:
    - `clean_cube`: 8 vertices, 12 faces, 1 component, watertight True, SUCCESS.
    - `disconnected`: 12 -> 8 vertices, 16 -> 12 faces, 2 -> 1 component, watertight True, SUCCESS.
    - `degenerate`: 11 -> 8 vertices, 13 -> 12 faces, zero-area face and unreferenced vertices removed, watertight True, SUCCESS.
    - `hole`: 8 -> 8 vertices, 11 -> 12 faces, boundary loop repaired, watertightness restored, SUCCESS.
  - CLI smoke test verified: `python -m loom geometry --input outputs/experiments/phase3_validation/hole.obj` completed with exit code 0, generated valid intermediate mesh and `reports/geometry.json`.
- **Next Step**:
  - Unblock host photogrammetry backend (`ISSUE-BLK-002`) to run live smartphone video through Phase 1 -> Phase 2 -> Phase 3 end-to-end.
  - Begin Phase 4 (Fiducial Metric Scaling & Coordinate Transformation).

---

## Iteration 022 — Unified Turbo Video-to-3D-Print Pipeline (< 200s Total Runtime Benchmark)
- **Date**: 2026-11-10
- **Milestone**: Phase 1 / Phase 2 / Phase 3 / Phase 4 / Phase 7 / Phase 8 — End-to-End Turbo Pipeline Benchmark Verified
- **Context & Motivation**:
  - Processing hundreds of unconstrained video frames through unoptimized photogrammetry caused 25+ minute bottlenecks, thermal throttling, and memory crashes.
  - Requirement: End-to-end turnaround under 200s (3.5 minutes) from raw smartphone video to a 100% watertight, validated, 2-manifold binary STL.
- **Changes Implemented**:
  - Video Ingest & Downscaling (`src/loom/video/frames.py`, `src/loom/config/models.py`):
    - Added `target_max_dimension: Optional[int] = 960` and `turbo: bool = False` to `VideoConfig`.
    - Downscaled extracted keyframes using `cv2.INTER_AREA` when $\max(H, W) > 960$.
    - In `--turbo` mode, defaulted `max_frames = 36` with even duration striding and Laplacian blur filtering.
  - Live Subprocess Streaming (`src/loom/utils/subprocess.py`):
    - Re-architected `run_subprocess()` with `stream_output=True` using `subprocess.Popen` and daemon pipe reader threads to stream live progress to stdout/stderr while capturing full output.
  - Reconstruction Acceleration (`src/loom/reconstruction/colmap.py`):
    - Added `turbo` flag to `ColmapAdapter.run_matching()`, `run_mapper()`, `run_stereo_fusion()`, and `reconstruct_dense()`.
    - Matching: GPU sequential matching with `overlap=5`, `quadratic_overlap=0`.
    - Mapper: 16 threads, bounded bundle adjustment iterations (`ba_global=12`, `ba_local=10`).
    - Dense MVS: Single-pass photometric stereo (`window_radius=4`, `num_iterations=3`, `geom_consistency=False`, `max_image_size=960`).
    - Meshing: Poisson mesher at depth 9 with `trim=0` directly on `fused.ply` containing native normal vectors.
  - Planar Base Capping with `mapbox-earcut` (`src/loom/mesh/repair.py`):
    - Replaced centroid fan triangulation on base cut loops with `mapbox_earcut.triangulate_float64` (with fallback to pure ear clipping), eliminating self-intersections on non-convex soles.
    - Verified outward downward normal orientation ($n_z < 0$) for all base cap triangles.
  - CLI Turbo Pipeline Integration (`scripts/demo.py`):
    - Added `--turbo` flag auto-configuring `max_frames=36`, `max_image_size=960`, `dense=True`, `align_support=True`, `clean_mesh=True`, `remove_floor=True`, `cap_base=True`, and `base_z=0.005`.
    - Added graceful video path resolution falling back to repository candidates (`data/raw/shoe_2.mp4`).
  - Unit Tests:
    - Added `test_colmap_adapter_turbo_flags` and `test_demo_turbo_cli` in `tests/unit/reconstruction/test_colmap_adapter.py`.
    - Total test suite: 240 passed in 4.55s.
- **Empirical Verification (`outputs/turbo_run`)**:
  - Command: `.venv/bin/python scripts/demo.py --video data/raw/shoe_2.mp4 --output-dir outputs/turbo_run --turbo --target-length 280.0 --export-stl`
  - Total end-to-end turnaround: **151.0 seconds** (2.5 minutes, beating < 200s target).
  - Frame extraction: 36 frames downscaled to $540 \times 960$ in 51.8s.
  - Sparse SfM: SIFT GPU extraction + sequential matching + 16-thread mapper in 7.0s.
  - Dense MVS & Meshing: 88.69s (photometric stereo in 25s, fusion 183k points, Poisson mesher 65,666 verts in 1.6s).
  - Canonical Alignment: RANSAC support plane normal $[0.163, -0.541, -0.825]$ rotated to $[0, 0, 1]^T$ at $Z=0$.
  - Phase 3 Cleaning & Planar Slicing: 5,415 `mapbox-earcut` cap faces across 65 loops at $Z=0.005$.
  - Target Scaling: Uniform scaling ($s=22.78428$) to 280.0 mm in float64 memory.
  - Printability Gate: **PASSED** (watertight=True, 0 boundary edges, 0 non-manifold edges, 0 non-manifold vertices, volume=$448,368.5\,\text{mm}^3$).
  - Binary STL Exported: `outputs/stl/cleaned_aligned_meshed-poisson_metric.stl` (86,850 faces, 4,342,584 bytes).
  - JSON Manifest: `outputs/stl/cleaned_aligned_meshed-poisson_metric_manifest.json`.

---



---

## Iteration 004 — Phase 2: Architecture, Contracts, Failure Classification & Pipeline Integration

- **Date**: 2026-09-26
- **Milestone**: Phase 2 — Multi-View 3D Reconstruction Integration (Architecture & Adapter: IMPLEMENTED & VERIFIED with 75 tests; Live execution: BLOCKED pending host binary)
- **Changes Implemented**:
  - Enforced strict Phase 2 architectural boundaries: zero Phase 3+ functionality added (no mesh cleanup, no hole repair, no metric scaling, no ArUco detection, no STL export, no heavyweight AI dependencies).
  - Explicitly decoupled software implementation status from live reconstruction experimental validation status.
  - Defined explicit 7-state failure classification enumeration `ReconstructionStatus` (`SUCCESS`, `PARTIAL`, `BINARY_UNAVAILABLE`, `INVALID_INPUT`, `PROCESS_FAILED`, `TIMEOUT`, `ARTIFACT_MISSING`) in `src/loom/reconstruction/models.py`.
  - Defined 8 conceptual reconstruction stages via `ReconstructionStage` enum (Stage 0: Input Validation, Stage 1: Camera Init, Stage 2: Camera Registration, Stage 3: Sparse Reconstruction, Stage 4: Dense Reconstruction, Stage 5: Raw Meshing, Stage 6: Artifact Discovery, Stage 7: Diagnostics).
  - Expanded `ReconstructionResult` and `ReconstructionArtifact` models with decoupled multi-tier artifacts: `sparse_reconstruction_path`, `dense_point_cloud_path`, `raw_mesh_path`, `workspace_path`, `log_path`, `status`, and backward-compatible alias properties.
  - Extended exception hierarchy in `src/loom/reconstruction/exceptions.py` with `ReconstructionInvalidInputError` (inherits from `ValueError` and `FileNotFoundError` for backward compatibility), `ReconstructionTimeoutError` (inherits from `ReconstructionExecutionError`), and `ReconstructionPartialError`.
  - Hardened `MeshroomAdapter` in `src/loom/reconstruction/meshroom.py`:
    - Implemented `DiscoveredArtifacts` dataclass supporting 3-variable tuple unpacking (`mesh, pc, sfm`), sequence indexing, and dictionary access for 100% backward compatibility.
    - Explicitly distinguished dense point clouds (`densePointCloud.ply`, `pointCloud.ply`) from sparse SfM clouds (`cloud_and_poses.ply`, `sfm.ply`).
    - Handled partial reconstructions (`status=PARTIAL`) where sparse/dense point cloud and camera poses were generated but meshing failed or was not produced.
    - Handled missing artifacts (`status=ARTIFACT_MISSING`) when subprocess returns 0 without writing output files.
    - Attached `reconstruction.log` path to `ReconstructionResult`.
  - Updated `src/loom/pipeline/runner.py` and `reports/reconstruction.json` to write standardized schema containing `status`, `sparse_reconstruction`, `dense_point_cloud_path`, `point_cloud_path`, `workspace_path`, and `log_path`.
  - Enhanced CLI (`src/loom/__main__.py`) terminal summary output to display categorized failure state, sparse SFM cloud, dense point cloud, workspace, and log file paths.
  - Authored comprehensive Phase 2 architectural specification in `docs/reconstruction.md`.
  - Added 10 new tests: unit tests in `tests/unit/reconstruction/test_meshroom_adapter.py` (partial reconstruction, artifact missing, timeout subclass, invalid input error types, discovered artifacts properties, reconstruction stage sequence) and integration tests in `tests/integration/reconstruction/test_reconstruction_contract.py` and `tests/integration/video_pipeline/test_phase1_pipeline.py`.
- **Verification**:
  - Full test suite passed: **75 passed in 5.62s** (100% pass rate, zero regressions across all 75 tests).
  - CLI `--help` and `--dry-run` verified.
  - Synthetic pipeline with `--reconstruct` executed on `data/raw/synthetic_test.mp4`: verified graceful degradation (`BINARY_UNAVAILABLE`), non-crashing execution, valid `reports/reconstruction.json` output, and informative terminal summary.
- **Next Step**:
  - Install Meshroom 2023.3 on development host (or pass `--meshroom-path`) and provide a real smartphone capture to run live 3D reconstruction.

---

## Iteration 022 — Unified Turbo Video-to-3D-Print Pipeline (< 200s Total Runtime Benchmark)
- **Date**: 2026-11-10
- **Milestone**: Phase 1 / Phase 2 / Phase 3 / Phase 4 / Phase 7 / Phase 8 — End-to-End Turbo Pipeline Benchmark Verified
- **Context & Motivation**:
  - Processing hundreds of unconstrained video frames through unoptimized photogrammetry caused 25+ minute bottlenecks, thermal throttling, and memory crashes.
  - Requirement: End-to-end turnaround under 200s (3.5 minutes) from raw smartphone video to a 100% watertight, validated, 2-manifold binary STL.
- **Changes Implemented**:
  - Video Ingest & Downscaling (`src/loom/video/frames.py`, `src/loom/config/models.py`):
    - Added `target_max_dimension: Optional[int] = 960` and `turbo: bool = False` to `VideoConfig`.
    - Downscaled extracted keyframes using `cv2.INTER_AREA` when $\max(H, W) > 960$.
    - In `--turbo` mode, defaulted `max_frames = 36` with even duration striding and Laplacian blur filtering.
  - Live Subprocess Streaming (`src/loom/utils/subprocess.py`):
    - Re-architected `run_subprocess()` with `stream_output=True` using `subprocess.Popen` and daemon pipe reader threads to stream live progress to stdout/stderr while capturing full output.
  - Reconstruction Acceleration (`src/loom/reconstruction/colmap.py`):
    - Added `turbo` flag to `ColmapAdapter.run_matching()`, `run_mapper()`, `run_stereo_fusion()`, and `reconstruct_dense()`.
    - Matching: GPU sequential matching with `overlap=5`, `quadratic_overlap=0`.
    - Mapper: 16 threads, bounded bundle adjustment iterations (`ba_global=12`, `ba_local=10`).
    - Dense MVS: Single-pass photometric stereo (`window_radius=4`, `num_iterations=3`, `geom_consistency=False`, `max_image_size=960`).
    - Meshing: Poisson mesher at depth 9 with `trim=0` directly on `fused.ply` containing native normal vectors.
  - Planar Base Capping with `mapbox-earcut` (`src/loom/mesh/repair.py`):
    - Replaced centroid fan triangulation on base cut loops with `mapbox_earcut.triangulate_float64` (with fallback to pure ear clipping), eliminating self-intersections on non-convex soles.
    - Verified outward downward normal orientation ($n_z < 0$) for all base cap triangles.
  - CLI Turbo Pipeline Integration (`scripts/demo.py`):
    - Added `--turbo` flag auto-configuring `max_frames=36`, `max_image_size=960`, `dense=True`, `align_support=True`, `clean_mesh=True`, `remove_floor=True`, `cap_base=True`, and `base_z=0.005`.
    - Added graceful video path resolution falling back to repository candidates (`data/raw/shoe_2.mp4`).
  - Unit Tests:
    - Added `test_colmap_adapter_turbo_flags` and `test_demo_turbo_cli` in `tests/unit/reconstruction/test_colmap_adapter.py`.
    - Total test suite: 240 passed in 4.55s.
- **Empirical Verification (`outputs/turbo_run`)**:
  - Command: `.venv/bin/python scripts/demo.py --video data/raw/shoe_2.mp4 --output-dir outputs/turbo_run --turbo --target-length 280.0 --export-stl`
  - Total end-to-end turnaround: **151.0 seconds** (2.5 minutes, beating < 200s target).
  - Frame extraction: 36 frames downscaled to $540 \times 960$ in 51.8s.
  - Sparse SfM: SIFT GPU extraction + sequential matching + 16-thread mapper in 7.0s.
  - Dense MVS & Meshing: 88.69s (photometric stereo in 25s, fusion 183k points, Poisson mesher 65,666 verts in 1.6s).
  - Canonical Alignment: RANSAC support plane normal $[0.163, -0.541, -0.825]$ rotated to $[0, 0, 1]^T$ at $Z=0$.
  - Phase 3 Cleaning & Planar Slicing: 5,415 `mapbox-earcut` cap faces across 65 loops at $Z=0.005$.
  - Target Scaling: Uniform scaling ($s=22.78428$) to 280.0 mm in float64 memory.
  - Printability Gate: **PASSED** (watertight=True, 0 boundary edges, 0 non-manifold edges, 0 non-manifold vertices, volume=$448,368.5\,\text{mm}^3$).
  - Binary STL Exported: `outputs/stl/cleaned_aligned_meshed-poisson_metric.stl` (86,850 faces, 4,342,584 bytes).
  - JSON Manifest: `outputs/stl/cleaned_aligned_meshed-poisson_metric_manifest.json`.

---



---

## Iteration 003 — Phase 1.5 Verification & Hardening, Phase 2: Meshroom 3D Reconstruction Adapter
- **Date**: 2026-09-26
- **Milestone**: Phase 2 — Multi-View 3D Reconstruction Integration (IMPLEMENTED & VERIFIED with mocked subprocess; Live execution BLOCKED by host binary)
- **Changes Implemented**:
  - Independently verified Phase 1 baseline test suite: exactly 52 tests passed in 3.59s with 0 failures, 0 warnings.
  - Fixed documentation drift across the repository: replaced stale `src/video2print/` references with actual `src/loom/` in `project/ROADMAP.md` and `.agents/rules/architecture.md`.
  - Conducted host environment discovery: searched system PATH, standard Windows program directories, and winget registry. Verified that `meshroom_batch`, `aliceVision_*`, and `colmap` are not installed on the development host (`ISSUE-BLK-002`).
  - Extended configuration models (`src/loom/config/models.py`, `loader.py`, `configs/*.yaml`) to support `binary_path: Optional[Path] = None`, `keep_workspace: bool = True`, and `additional_args: list[str]`.
  - Extended result models (`src/loom/reconstruction/models.py`) with `mesh_path`, `point_cloud_path`, `camera_poses_path`, `input_frames_count`, `registered_cameras_count`, `registration_ratio`, `point_count`, `error_message`, and `backend` alias.
  - Implemented typed reconstruction exceptions in `src/loom/reconstruction/exceptions.py`: `ReconstructionError`, `ReconstructionBinaryNotFoundError`, `ReconstructionExecutionError`, `ReconstructionArtifactNotFoundError`.
  - Implemented production `MeshroomAdapter` in `src/loom/reconstruction/meshroom.py`:
    - `resolve_binary()` and `is_available()` checking configuration overrides, environment variables (`MESHROOM_PATH`, `MESHROOM_BIN`), and system PATH.
    - CLI argument construction (`build_command()`) without shell invocation (`shell=False`).
    - AliceVision `cameras.sfm` JSON parser extracting registered camera count and registration ratio.
    - Multi-tier output artifact discovery (`discover_output_artifacts()`) locating `texturedMesh.obj/ply`, `mesh.obj/ply`, `cloud_and_poses.ply`, and `cameras.sfm`.
    - Isolated workspace layout (`outputs/runs/<run_id>/reconstruction/workspace/{input,output,cache,logs}`).
    - Subprocess execution using safe `proc.communicate(timeout=...)` with streaming log capture into `reconstruction.log`.
  - Implemented `ReconstructionRunner` in `src/loom/reconstruction/runner.py` with factory lookup and descriptive error for unsupported backends.
  - Integrated reconstruction into the pipeline runner (`src/loom/pipeline/runner.py`), directly feeding Phase 1 selected keyframes to the reconstruction adapter and generating `reports/reconstruction.json`.
  - Extended CLI (`src/loom/__main__.py`) with `--reconstruct` and `--meshroom-path` flags and comprehensive Phase 2 summary terminal output.
  - Created smartphone capture guide in `docs/capture/capture_guide.md` specifying physical target requirements, lighting, orbital trajectory (two elevation rings), and overlap requirements.
  - Created standalone diagnostic smoke test script in `scripts/reconstruction_smoke_test.py`.
  - Implemented 13 unit tests with mocked subprocess in `tests/unit/reconstruction/test_meshroom_adapter.py` testing missing binary, invalid inputs, command construction, SFM parsing, artifact discovery, successful runs, non-zero return codes, timeouts, and missing mesh failure reporting.
- **Verification**:
  - Full test suite passed: **65 passed in 4.60s** (13 new reconstruction tests + 52 existing tests, 100% pass rate).
  - CLI dry-run verified: `python -m loom --dry-run` passed.
  - CLI Phase 1 verified: `python -m loom --video data/raw/synthetic_test.mp4` passed.
  - CLI Phase 2 graceful degradation verified: `python -m loom --video data/raw/synthetic_test.mp4 --reconstruct` correctly reported missing binary, generated valid `reconstruction.json`, and displayed structured Phase 2 terminal summary.
- **Next Step**:
  - Install Meshroom 2023.3 on development host (or pass `--meshroom-path`) and provide a real smartphone capture to run live 3D reconstruction.

---

## Iteration 022 — Unified Turbo Video-to-3D-Print Pipeline (< 200s Total Runtime Benchmark)
- **Date**: 2026-11-10
- **Milestone**: Phase 1 / Phase 2 / Phase 3 / Phase 4 / Phase 7 / Phase 8 — End-to-End Turbo Pipeline Benchmark Verified
- **Context & Motivation**:
  - Processing hundreds of unconstrained video frames through unoptimized photogrammetry caused 25+ minute bottlenecks, thermal throttling, and memory crashes.
  - Requirement: End-to-end turnaround under 200s (3.5 minutes) from raw smartphone video to a 100% watertight, validated, 2-manifold binary STL.
- **Changes Implemented**:
  - Video Ingest & Downscaling (`src/loom/video/frames.py`, `src/loom/config/models.py`):
    - Added `target_max_dimension: Optional[int] = 960` and `turbo: bool = False` to `VideoConfig`.
    - Downscaled extracted keyframes using `cv2.INTER_AREA` when $\max(H, W) > 960$.
    - In `--turbo` mode, defaulted `max_frames = 36` with even duration striding and Laplacian blur filtering.
  - Live Subprocess Streaming (`src/loom/utils/subprocess.py`):
    - Re-architected `run_subprocess()` with `stream_output=True` using `subprocess.Popen` and daemon pipe reader threads to stream live progress to stdout/stderr while capturing full output.
  - Reconstruction Acceleration (`src/loom/reconstruction/colmap.py`):
    - Added `turbo` flag to `ColmapAdapter.run_matching()`, `run_mapper()`, `run_stereo_fusion()`, and `reconstruct_dense()`.
    - Matching: GPU sequential matching with `overlap=5`, `quadratic_overlap=0`.
    - Mapper: 16 threads, bounded bundle adjustment iterations (`ba_global=12`, `ba_local=10`).
    - Dense MVS: Single-pass photometric stereo (`window_radius=4`, `num_iterations=3`, `geom_consistency=False`, `max_image_size=960`).
    - Meshing: Poisson mesher at depth 9 with `trim=0` directly on `fused.ply` containing native normal vectors.
  - Planar Base Capping with `mapbox-earcut` (`src/loom/mesh/repair.py`):
    - Replaced centroid fan triangulation on base cut loops with `mapbox_earcut.triangulate_float64` (with fallback to pure ear clipping), eliminating self-intersections on non-convex soles.
    - Verified outward downward normal orientation ($n_z < 0$) for all base cap triangles.
  - CLI Turbo Pipeline Integration (`scripts/demo.py`):
    - Added `--turbo` flag auto-configuring `max_frames=36`, `max_image_size=960`, `dense=True`, `align_support=True`, `clean_mesh=True`, `remove_floor=True`, `cap_base=True`, and `base_z=0.005`.
    - Added graceful video path resolution falling back to repository candidates (`data/raw/shoe_2.mp4`).
  - Unit Tests:
    - Added `test_colmap_adapter_turbo_flags` and `test_demo_turbo_cli` in `tests/unit/reconstruction/test_colmap_adapter.py`.
    - Total test suite: 240 passed in 4.55s.
- **Empirical Verification (`outputs/turbo_run`)**:
  - Command: `.venv/bin/python scripts/demo.py --video data/raw/shoe_2.mp4 --output-dir outputs/turbo_run --turbo --target-length 280.0 --export-stl`
  - Total end-to-end turnaround: **151.0 seconds** (2.5 minutes, beating < 200s target).
  - Frame extraction: 36 frames downscaled to $540 \times 960$ in 51.8s.
  - Sparse SfM: SIFT GPU extraction + sequential matching + 16-thread mapper in 7.0s.
  - Dense MVS & Meshing: 88.69s (photometric stereo in 25s, fusion 183k points, Poisson mesher 65,666 verts in 1.6s).
  - Canonical Alignment: RANSAC support plane normal $[0.163, -0.541, -0.825]$ rotated to $[0, 0, 1]^T$ at $Z=0$.
  - Phase 3 Cleaning & Planar Slicing: 5,415 `mapbox-earcut` cap faces across 65 loops at $Z=0.005$.
  - Target Scaling: Uniform scaling ($s=22.78428$) to 280.0 mm in float64 memory.
  - Printability Gate: **PASSED** (watertight=True, 0 boundary edges, 0 non-manifold edges, 0 non-manifold vertices, volume=$448,368.5\,\text{mm}^3$).
  - Binary STL Exported: `outputs/stl/cleaned_aligned_meshed-poisson_metric.stl` (86,850 faces, 4,342,584 bytes).
  - JSON Manifest: `outputs/stl/cleaned_aligned_meshed-poisson_metric_manifest.json`.

---



---

## Iteration 002 — Phase 1: Video Ingest, Frame Extraction & Capture Quality
- **Date**: 2026-09-26
- **Milestone**: Phase 1 — Video Ingest, Frame Extraction & Capture Quality (COMPLETED)
- **Changes Implemented**:
  - Installed and pinned Phase 1 dependencies in Python 3.10.11 `.venv`: `numpy==2.2.6`, `opencv-python==5.0.0.93`, `tqdm==4.70.1`.
  - Implemented OpenCV-based video validation and container metadata extraction in `src/loom/video/metadata.py` with robust duration calculation, stream property validation, FourCC decoding, and deterministic `try...finally: cap.release()`.
  - Implemented `VideoIngestor` in `src/loom/video/ingest.py`, validating container formats and producing verified `VideoArtifact`.
  - Implemented sequential streaming frame extraction in `src/loom/video/frames.py` with configurable sampling interval, target FPS, max_frames, JPEG quality encoding, deterministic filenames (`frame_{idx:06d}.jpg`), and machine-readable `manifest.json`. Zero whole-video RAM retention.
  - Implemented deterministic optical quality analysis in `src/loom/capture/quality.py`:
    - Sharpness via Laplacian variance on grayscale images.
    - Brightness via grayscale mean (with configurable min/max exposure rejection).
    - Contrast via grayscale standard deviation (with configurable min contrast threshold).
    - Redundancy filtering via 64x64 thumbnail mean absolute difference against previous accepted frame (`redundancy_threshold=0.98`).
  - Implemented 2D viewpoint diversity estimation in `src/loom/capture/coverage.py` and actionable capture guidance generation in `src/loom/capture/guidance.py`.
  - Implemented Phase 1 pipeline execution in `src/loom/pipeline/runner.py` with standardized output directory structure (`outputs/runs/<run_id>/frames/{raw,selected}`, `reports/{metadata.json,capture_analysis.json}`, `logs/pipeline.log`).
  - Extended CLI (`src/loom/__main__.py`) supporting `--video`, `--config`, `--output-dir`, and outputting rich terminal execution summaries.
  - Completed synthetic test video generator `scripts/generate_test_video.py` producing controlled variations (normal, blurred, dark, bright, redundant frames).
  - Built comprehensive unit tests (`test_metadata.py`, `test_frames.py`, `test_quality.py`) and end-to-end integration tests (`test_phase1_pipeline.py`).
- **Verification**:
  - `pytest tests/ -v` passed all 52 tests (100% pass rate).
  - Synthetic video generation tested: 60 frames @ 30 FPS, 640x480 generated and verified.
  - CLI execution verified: `python -m loom --video data/raw/synthetic_test.mp4` successfully ran end-to-end, extracted 60 frames, filtered defects, copied 5 high-quality keyframes to `frames/selected/`, and generated both JSON reports and log file.
  - Memory & resource safety verified: streaming extraction consumes constant minimal memory (< 80 MB) without accumulative memory growth.
- **Next Step**:
  - Phase 2 Planning: Multi-View 3D Reconstruction Integration (Meshroom / AliceVision CLI adapter).

---

## Iteration 022 — Unified Turbo Video-to-3D-Print Pipeline (< 200s Total Runtime Benchmark)
- **Date**: 2026-11-10
- **Milestone**: Phase 1 / Phase 2 / Phase 3 / Phase 4 / Phase 7 / Phase 8 — End-to-End Turbo Pipeline Benchmark Verified
- **Context & Motivation**:
  - Processing hundreds of unconstrained video frames through unoptimized photogrammetry caused 25+ minute bottlenecks, thermal throttling, and memory crashes.
  - Requirement: End-to-end turnaround under 200s (3.5 minutes) from raw smartphone video to a 100% watertight, validated, 2-manifold binary STL.
- **Changes Implemented**:
  - Video Ingest & Downscaling (`src/loom/video/frames.py`, `src/loom/config/models.py`):
    - Added `target_max_dimension: Optional[int] = 960` and `turbo: bool = False` to `VideoConfig`.
    - Downscaled extracted keyframes using `cv2.INTER_AREA` when $\max(H, W) > 960$.
    - In `--turbo` mode, defaulted `max_frames = 36` with even duration striding and Laplacian blur filtering.
  - Live Subprocess Streaming (`src/loom/utils/subprocess.py`):
    - Re-architected `run_subprocess()` with `stream_output=True` using `subprocess.Popen` and daemon pipe reader threads to stream live progress to stdout/stderr while capturing full output.
  - Reconstruction Acceleration (`src/loom/reconstruction/colmap.py`):
    - Added `turbo` flag to `ColmapAdapter.run_matching()`, `run_mapper()`, `run_stereo_fusion()`, and `reconstruct_dense()`.
    - Matching: GPU sequential matching with `overlap=5`, `quadratic_overlap=0`.
    - Mapper: 16 threads, bounded bundle adjustment iterations (`ba_global=12`, `ba_local=10`).
    - Dense MVS: Single-pass photometric stereo (`window_radius=4`, `num_iterations=3`, `geom_consistency=False`, `max_image_size=960`).
    - Meshing: Poisson mesher at depth 9 with `trim=0` directly on `fused.ply` containing native normal vectors.
  - Planar Base Capping with `mapbox-earcut` (`src/loom/mesh/repair.py`):
    - Replaced centroid fan triangulation on base cut loops with `mapbox_earcut.triangulate_float64` (with fallback to pure ear clipping), eliminating self-intersections on non-convex soles.
    - Verified outward downward normal orientation ($n_z < 0$) for all base cap triangles.
  - CLI Turbo Pipeline Integration (`scripts/demo.py`):
    - Added `--turbo` flag auto-configuring `max_frames=36`, `max_image_size=960`, `dense=True`, `align_support=True`, `clean_mesh=True`, `remove_floor=True`, `cap_base=True`, and `base_z=0.005`.
    - Added graceful video path resolution falling back to repository candidates (`data/raw/shoe_2.mp4`).
  - Unit Tests:
    - Added `test_colmap_adapter_turbo_flags` and `test_demo_turbo_cli` in `tests/unit/reconstruction/test_colmap_adapter.py`.
    - Total test suite: 240 passed in 4.55s.
- **Empirical Verification (`outputs/turbo_run`)**:
  - Command: `.venv/bin/python scripts/demo.py --video data/raw/shoe_2.mp4 --output-dir outputs/turbo_run --turbo --target-length 280.0 --export-stl`
  - Total end-to-end turnaround: **151.0 seconds** (2.5 minutes, beating < 200s target).
  - Frame extraction: 36 frames downscaled to $540 \times 960$ in 51.8s.
  - Sparse SfM: SIFT GPU extraction + sequential matching + 16-thread mapper in 7.0s.
  - Dense MVS & Meshing: 88.69s (photometric stereo in 25s, fusion 183k points, Poisson mesher 65,666 verts in 1.6s).
  - Canonical Alignment: RANSAC support plane normal $[0.163, -0.541, -0.825]$ rotated to $[0, 0, 1]^T$ at $Z=0$.
  - Phase 3 Cleaning & Planar Slicing: 5,415 `mapbox-earcut` cap faces across 65 loops at $Z=0.005$.
  - Target Scaling: Uniform scaling ($s=22.78428$) to 280.0 mm in float64 memory.
  - Printability Gate: **PASSED** (watertight=True, 0 boundary edges, 0 non-manifold edges, 0 non-manifold vertices, volume=$448,368.5\,\text{mm}^3$).
  - Binary STL Exported: `outputs/stl/cleaned_aligned_meshed-poisson_metric.stl` (86,850 faces, 4,342,584 bytes).
  - JSON Manifest: `outputs/stl/cleaned_aligned_meshed-poisson_metric_manifest.json`.

---



---

## Iteration 001 — Complete Application Scaffold & Test Hierarchy
- **Date**: 2026-09-26
- **Milestone**: Phase 0 — Application Scaffold & Architecture
- **Changes Implemented**:
  - Installed Python 3.10.11 64-bit on host via winget and activated virtual environment `.venv/` resolving `ISSUE-BLK-001`.
  - Created standard src-layout package `src/loom/` with `pyproject.toml` supporting `python -m loom` CLI.
  - Implemented typed configuration system (`src/loom/config/`) with YAML parser and preset profiles (`configs/default.yaml`, `configs/development.yaml`, `configs/experiment.yaml`).
  - Implemented immutable artifact model (`src/loom/pipeline/artifacts.py`) and pipeline stage contracts (`src/loom/pipeline/stages.py`, `src/loom/pipeline/runner.py`) supporting dry-run verification.
  - Implemented 3D geometric math models (`src/loom/geometry/`) including `Point3D`, `Vector3D`, `BoundingBox3D`, and `TransformMatrix4x4`.
  - Scaffolded interfaces and data contracts across all pipeline stages:
    - `src/loom/video/`: VideoIngestor, VideoMetadata, FrameExtractor (streaming contract)
    - `src/loom/capture/`: FrameQualityAssessor, CoverageEstimator, CaptureGuidance
    - `src/loom/reconstruction/`: ReconstructionEngine ABC, MeshroomAdapter, ColmapAdapter, ReconstructionRunner
    - `src/loom/pointcloud/`: PointCloudCleaner, PointCloudFilter, PointCloudAnalyzer
    - `src/loom/mesh/`: MeshCleaner, MeshRepairer, MeshTopologyAnalyzer, SurfaceReconstructor
    - `src/loom/scaling/`: ArucoDetector, ScaleCalibrator, ScaleTransformer
    - `src/loom/validation/`: DimensionAnalyzer, GeometryComparator, GroundTruthComparison, ValidationReportGenerator
    - `src/loom/printability/`: ManifoldChecker, WatertightChecker, WallThicknessAnalyzer, OverhangAnalyzer, PrintabilityReportGenerator
    - `src/loom/export/`: StlExporter, ExportManifest, ExportReportGenerator
    - `src/loom/utils/`: logging, paths, subprocess, hashing
  - Created test suite hierarchy under `tests/` with 35 unit and integration tests across package imports, configs, artifacts, runner dry-run, geometry math, and stage contracts.
  - Created utility and diagnostic scripts under `scripts/`: `environment_check.py`, `generate_test_video.py`, `generate_marker.py`, `benchmark.py`.
  - Created directory scaffolding for `data/`, `outputs/`, and `docs/` with `.gitkeep` placeholders.
  - Authored architecture overview documentation in `docs/architecture/overview.md`.
  - Updated `README.md` to clearly distinguish Implemented, Scaffolded, and Planned subsystems.
  - Updated `project/CONTEXT.md` and `project/ISSUES.md` (resolved `ISSUE-BLK-001`).
- **Verification**:
  - `python -m loom --help`, `python -m loom --dry-run`, and `python -m loom -c configs/default.yaml --dry-run` execute cleanly.
  - `pytest tests/ -v` passes 35 out of 35 tests with 0 failures and 0 warnings.
  - `scripts/environment_check.py` successfully diagnoses runtime and dependency status.
  - Verified no circular imports, no fake photogrammetry/meshing logic, and proper `NotImplementedError` boundaries on scaffolded interfaces.
- **Next Step**:
  - Phase 1 Kickoff: Implement real streaming video ingest, frame extraction, and Laplacian sharpness quality filtering using OpenCV.

---

## Iteration 022 — Unified Turbo Video-to-3D-Print Pipeline (< 200s Total Runtime Benchmark)
- **Date**: 2026-11-10
- **Milestone**: Phase 1 / Phase 2 / Phase 3 / Phase 4 / Phase 7 / Phase 8 — End-to-End Turbo Pipeline Benchmark Verified
- **Context & Motivation**:
  - Processing hundreds of unconstrained video frames through unoptimized photogrammetry caused 25+ minute bottlenecks, thermal throttling, and memory crashes.
  - Requirement: End-to-end turnaround under 200s (3.5 minutes) from raw smartphone video to a 100% watertight, validated, 2-manifold binary STL.
- **Changes Implemented**:
  - Video Ingest & Downscaling (`src/loom/video/frames.py`, `src/loom/config/models.py`):
    - Added `target_max_dimension: Optional[int] = 960` and `turbo: bool = False` to `VideoConfig`.
    - Downscaled extracted keyframes using `cv2.INTER_AREA` when $\max(H, W) > 960$.
    - In `--turbo` mode, defaulted `max_frames = 36` with even duration striding and Laplacian blur filtering.
  - Live Subprocess Streaming (`src/loom/utils/subprocess.py`):
    - Re-architected `run_subprocess()` with `stream_output=True` using `subprocess.Popen` and daemon pipe reader threads to stream live progress to stdout/stderr while capturing full output.
  - Reconstruction Acceleration (`src/loom/reconstruction/colmap.py`):
    - Added `turbo` flag to `ColmapAdapter.run_matching()`, `run_mapper()`, `run_stereo_fusion()`, and `reconstruct_dense()`.
    - Matching: GPU sequential matching with `overlap=5`, `quadratic_overlap=0`.
    - Mapper: 16 threads, bounded bundle adjustment iterations (`ba_global=12`, `ba_local=10`).
    - Dense MVS: Single-pass photometric stereo (`window_radius=4`, `num_iterations=3`, `geom_consistency=False`, `max_image_size=960`).
    - Meshing: Poisson mesher at depth 9 with `trim=0` directly on `fused.ply` containing native normal vectors.
  - Planar Base Capping with `mapbox-earcut` (`src/loom/mesh/repair.py`):
    - Replaced centroid fan triangulation on base cut loops with `mapbox_earcut.triangulate_float64` (with fallback to pure ear clipping), eliminating self-intersections on non-convex soles.
    - Verified outward downward normal orientation ($n_z < 0$) for all base cap triangles.
  - CLI Turbo Pipeline Integration (`scripts/demo.py`):
    - Added `--turbo` flag auto-configuring `max_frames=36`, `max_image_size=960`, `dense=True`, `align_support=True`, `clean_mesh=True`, `remove_floor=True`, `cap_base=True`, and `base_z=0.005`.
    - Added graceful video path resolution falling back to repository candidates (`data/raw/shoe_2.mp4`).
  - Unit Tests:
    - Added `test_colmap_adapter_turbo_flags` and `test_demo_turbo_cli` in `tests/unit/reconstruction/test_colmap_adapter.py`.
    - Total test suite: 240 passed in 4.55s.
- **Empirical Verification (`outputs/turbo_run`)**:
  - Command: `.venv/bin/python scripts/demo.py --video data/raw/shoe_2.mp4 --output-dir outputs/turbo_run --turbo --target-length 280.0 --export-stl`
  - Total end-to-end turnaround: **151.0 seconds** (2.5 minutes, beating < 200s target).
  - Frame extraction: 36 frames downscaled to $540 \times 960$ in 51.8s.
  - Sparse SfM: SIFT GPU extraction + sequential matching + 16-thread mapper in 7.0s.
  - Dense MVS & Meshing: 88.69s (photometric stereo in 25s, fusion 183k points, Poisson mesher 65,666 verts in 1.6s).
  - Canonical Alignment: RANSAC support plane normal $[0.163, -0.541, -0.825]$ rotated to $[0, 0, 1]^T$ at $Z=0$.
  - Phase 3 Cleaning & Planar Slicing: 5,415 `mapbox-earcut` cap faces across 65 loops at $Z=0.005$.
  - Target Scaling: Uniform scaling ($s=22.78428$) to 280.0 mm in float64 memory.
  - Printability Gate: **PASSED** (watertight=True, 0 boundary edges, 0 non-manifold edges, 0 non-manifold vertices, volume=$448,368.5\,\text{mm}^3$).
  - Binary STL Exported: `outputs/stl/cleaned_aligned_meshed-poisson_metric.stl` (86,850 faces, 4,342,584 bytes).
  - JSON Manifest: `outputs/stl/cleaned_aligned_meshed-poisson_metric_manifest.json`.

---



---

## Iteration 000 — Project Bootstrap & Agent Operating System
- **Date**: 2026-09-26
- **Milestone**: Phase 0 — Project Bootstrap
- **Changes Implemented**:
  - Inspected repository state (clean git working tree on branch `main`, Python 3.10.11 registered in `py` launcher but binary missing on disk; active host Python is 3.14.7).
  - Created project constitution [`AGENTS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/AGENTS.md) with core directives, mandatory iteration workflow, and context update protocols.
  - Created architectural rules in [`.agents/rules/architecture.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/architecture.md) detailing pipeline stages, interfaces, and backend replaceability.
  - Created Python standards in [`.agents/rules/python.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/python.md) specifying Python 3.10.11 runtime, lean dependency policy, and logging/path conventions.
  - Created 3D reconstruction rules in [`.agents/rules/reconstruction.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/reconstruction.md) detailing subprocess adapter pattern, monocular scale ambiguity, and ArUco marker scaling.
  - Created testing philosophy in [`.agents/rules/testing.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/testing.md) establishing independent testability and synthetic test fixtures.
  - Created research integrity rules in [`.agents/rules/research.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/research.md) enforcing zero fabrication of measurements or results.
  - Created current state snapshot in [`project/CONTEXT.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/CONTEXT.md).
  - Created 11-phase staged development plan in [`project/ROADMAP.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/ROADMAP.md).
  - Documented four initial Architecture Decision Records in [`project/DECISIONS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/DECISIONS.md) (ADR-001 through ADR-004).
  - Established schema and empirical logging rules in [`project/EXPERIMENTS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/EXPERIMENTS.md).
  - Recorded initial discoveries, limitations, and research questions in [`project/ISSUES.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/ISSUES.md).
- **Verification**:
  - Validated all 12 project governance and rule files created.
  - Verified no implementation code was falsely marked complete.
  - Verified internal consistency across rules, roadmap, ADRs, and issues.
- **Next Step**:
  - Begin Phase 1: Initialize `.venv` with Python 3.10.11, pin core dependencies in `requirements.txt`, and implement video ingest / frame extraction module with unit tests.
