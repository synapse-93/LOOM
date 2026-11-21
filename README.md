# LOOM (VIDEO2PRINT)

**Smartphone Video → Metrically Scaled → Validated → 3D Printable Binary STL**

LOOM is an end-to-end photogrammetry and computational geometry pipeline that converts an unconstrained tabletop smartphone video of an arbitrary physical object into a canonically aligned, metrically scaled, watertight, 2-manifold binary `.stl` file with a guaranteed flat build-plate base.

---

## Pipeline Overview

1. **Video Ingest (`src/loom/video/`)**: Extracts strided keyframes (68 frames in `--turbo`), downscales $\max(W, H) = 960\text{ px}$ with `cv2.INTER_AREA`, and rejects motion-blurred frames (Laplacian variance $< 18.0$).
2. **Sparse SfM + Circuit Breaker (`src/loom/reconstruction/colmap.py`)**: Runs COLMAP 4.2.0 CUDA SIFT extraction, GPU sequential matching (`overlap=10`, `quadratic_overlap=1`, `loop_detection=1`), and 16-thread mapping. Aborts with `RuntimeError` if registered camera views fall below 75% of input keyframes.
3. **Dense MVS (`src/loom/reconstruction/colmap.py`)**: Runs `image_undistorter`, CUDA `patch_match_stereo`, and `stereo_fusion` (`min_num_pixels=3` in turbo) to produce `dense/fused.ply` with surface normals `(nx, ny, nz)`.
4. **Canonical Alignment & Foreground Isolation (`src/loom/geometry/`)**: Detects the support surface via full-cloud vectorized RANSAC, enforces upward gravity polarity toward the COLMAP camera centroid ($\mathbf{n} \cdot (\mathbf{C}_{\text{cam}} - \mathbf{p}_0) > 0$), synchronously rotates vertices and unit normals via Rodrigues $SO(3)$ to $[0, 0, 1]^T$ at $Z = 0$, and crops background clutter (`fused_isolated.ply`).
5. **Screened Poisson Meshing (`src/loom/reconstruction/colmap.py`)**: Runs `colmap poisson_mesher` at `--PoissonMeshing.depth 10 --PoissonMeshing.trim 0 --PoissonMeshing.point_weight 1.0`.
6. **Mesh Repair & Planar Base Capping (`src/loom/mesh/`)**: Slices the base flat at $Z = 0.005$, seals boundary loops via `mapbox-earcut` ($n_z < 0$), decomposes figure-8 pinch loops, and rejects starburst capping on loops $> 60$ edges.
7. **Metric Scaling & Build-Plate Snap (`src/loom/scaling/`, `scripts/demo.py`)**: Applies ArUco fiducial scaling (`DICT_5X5_100`) when detected, or uniform `float64` scaling to `--target-length` (default `200.0` mm), snapping the flat base flush to $Z_{\min} = 0.000000\text{ mm}$.
8. **Printability Gate & STL Export (`src/loom/printability/`, `src/loom/export/`)**: Verifies watertightness, 2-manifoldness, and positive volume, exporting a validated binary `.stl` and companion JSON manifest.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for full module boundaries and geometric invariants.

---

## Host Requirements (Linux + CUDA)

- **OS:** Linux x86_64
- **GPU:** NVIDIA CUDA-capable GPU (tested on NVIDIA GeForce RTX 4060 Laptop GPU, 8 GB VRAM, CUDA 13.x)
- **COLMAP:** Native CUDA-enabled COLMAP 4.2.0 at `/usr/bin/colmap` (with `/opt/cuda/lib64` automatically prepended to `LD_LIBRARY_PATH` by `src/loom/utils/subprocess.py`)
- **Python Environment:** Local virtual environment at `.venv/`
- **Core Python Dependencies:** `numpy`, `scipy`, `trimesh`, `mapbox-earcut`, `opencv-python`, `pyyaml`, `pytest` (`open3d` is strictly optional)

---

## Quickstart

### 1. Run Automated Test Suite
```bash
.venv/bin/pytest tests/ -q
```
Current verified status: **248 passed** (unit and integration tests covering video ingest, COLMAP adapter, canonical alignment, foreground segmentation, mesh repair, scaling, printability gate, and STL export).

### 2. Verify COLMAP CUDA Linker via LOOM Subprocess Wrapper
```bash
.venv/bin/python -c "from loom.utils.subprocess import run_subprocess; r = run_subprocess(['colmap', '-h'], stream_output=False); print(r.stdout.splitlines()[0])"
```

### 3. End-to-End Turbo Video-to-STL Run
```bash
.venv/bin/python scripts/demo.py \
  --video data/raw/your_object.mp4 \
  --output-dir outputs/demo \
  --turbo \
  --target-length 200.0 \
  --export-stl
```

### 4. High-Resolution Standard Dense MVS Run (Geometric Consistency)
```bash
.venv/bin/python scripts/demo.py \
  --video data/raw/your_object.mp4 \
  --output-dir outputs/demo_hq \
  --dense \
  --align-support \
  --clean-mesh \
  --cap-base \
  --target-length 200.0 \
  --export-stl
```

### 5. Mesh-Only Processing (Skip Video & COLMAP)
```bash
.venv/bin/python scripts/demo.py \
  --mesh-only outputs/demo/dense/meshed-poisson.ply \
  --point-cloud outputs/demo/dense/fused.ply \
  --align-support \
  --clean-mesh \
  --cap-base \
  --target-length 200.0 \
  --export-stl
```

---

## Directory Layout

```text
LOOM/
├── ARCHITECTURE.md             # 8-stage system architecture and invariants
├── AGENTS.md                   # Agent constitution and iteration workflow
├── configs/                    # YAML configuration presets
├── data/                       # Raw videos & intermediate datasets (git-ignored)
├── outputs/                    # Reconstructions, meshes, and STLs (git-ignored)
├── project/                    # Project state (CONTEXT, CHANGELOG, DECISIONS, ISSUES)
├── scripts/                    # CLI runners (demo.py, align_and_isolate.py, etc.)
├── src/loom/                   # Core Python package
│   ├── capture/                # Sharpness, exposure, and coverage metrics
│   ├── config/                 # Typed configuration models and YAML loader
│   ├── export/                 # Validated binary STL exporter & manifests
│   ├── geometry/               # RANSAC alignment, Rodrigues SO(3), segmentation
│   ├── mesh/                   # Cleanup, KDTree culling, earcut base capping, repair
│   ├── pipeline/               # Pipeline runner, stages, and artifact contracts
│   ├── pointcloud/             # Point cloud diagnostics
│   ├── printability/           # Watertight, 2-manifold, overhang, PrintabilityGate
│   ├── reconstruction/         # ColmapAdapter & MeshroomAdapter backends
│   ├── scaling/                # ArUco fiducial detection & multi-view DLT scaling
│   ├── utils/                  # CUDA-aware subprocess, paths, hashing, logging
│   ├── validation/             # AABB/OBB dimensions & ground-truth error metrics
│   └── video/                  # Frame extraction, downscaling, blur rejection
└── tests/                      # Automated unit & integration test suite (248 tests)
```
