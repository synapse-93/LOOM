# LOOM (VIDEO2PRINT) — System Architecture

**Objective:** Deterministic conversion of unconstrained tabletop smartphone video into a metrically scaled, watertight, 2-manifold, build-plate-flush binary STL ready for 3D printing.

---

## 1. End-to-End 8-Stage Pipeline

```text
[ Smartphone Video (.mp4 / .mov) ]
              │
              ▼
 1. Video Ingest & Blur Filtering        src/loom/video/frames.py
    • Evenly strided keyframe sampling (68 frames in --turbo)
    • Downscaling max(W, H) = 960 px via cv2.INTER_AREA
    • Laplacian sharpness gating (variance >= 18.0)
              │
              ▼
 2. Sparse SfM & Circuit Breaker         src/loom/reconstruction/colmap.py
    • COLMAP 4.2.0 CUDA SIFT feature_extractor
    • GPU sequential_matcher (overlap=10, quadratic_overlap=1, loop_detection=1)
    • 16-thread mapper (min_num_matches=15, BA 15/12 in turbo, 20/15 standard)
    • SfM Circuit Breaker: parses sparse/0/images.bin; aborts with RuntimeError
      if registered views < 75% of input keyframes
              │
              ▼
 3. Dense MVS Stereo & Fusion            src/loom/reconstruction/colmap.py
    • colmap image_undistorter -> patch_match_stereo (CUDA gpu_index=0)
    • Turbo: max_image_size=960, window_radius=4, num_iterations=3, photometric
    • Standard: max_image_size=1600, window_radius=5, num_iterations=5, geometric
    • colmap stereo_fusion (min_num_pixels=3 turbo / 2 standard) -> dense/fused.ply
      with native surface normals (nx, ny, nz)
              │
              ▼
 4. Canonical Frame Normalization        src/loom/geometry/alignment.py
    & Foreground Isolation               src/loom/geometry/segmentation.py
    • Full-cloud vectorized RANSAC support plane fit (1500 iters, no camera-Z clip)
    • Camera-Centroid Upward Gravity Polarity: asserts n · (C_cam - p0) > 0
      using camera centers C = -R^T t from sparse/0/images.bin (median fallback)
    • Rodrigues SO(3) rotation R mapping n -> [0, 0, 1]^T applied synchronously
      to vertices (x, y, z) AND unit normal vectors (nx, ny, nz)
    • Support plane translated to Z = 0.0; elevated median centered at (X=0, Y=0)
    • ForegroundSegmenter: culls subsurface noise (Z < -0.005) and applies
      cKDTree elevated clustering + cylindrical crop (1.30 * R_98) -> fused_isolated.ply
              │
              ▼
 5. Screened Poisson Surface Meshing     src/loom/reconstruction/colmap.py
    • colmap poisson_mesher on fused_isolated.ply (or fused.ply)
    • Locked parameters: --PoissonMeshing.depth 10, --PoissonMeshing.trim 0,
      --PoissonMeshing.point_weight 1.0 (closed zero-crossing surface)
    • Automatic dense Delaunay fallback if Poisson produces 0 vertices
              │
              ▼
 6. Mesh Cleanup, Planar Base Cap        src/loom/mesh/processor.py
    & Anti-Starburst Topology Repair     src/loom/mesh/repair.py
    • Optional KDTree distance culling (3.5x spacing) & component isolation
    • Horizontal planar base cut at Z = 0.005 (parallel to canonical support plane)
    • Base boundary loop triangulation via mapbox-earcut (nz < 0 downward normal)
    • Figure-8 pinch decomposition (split_into_simple_cycles)
    • Anti-starburst guard: rejects conservative hole-filling on loops > 60 edges
    • Outward winding enforcement (positive signed volume)
              │
              ▼
 7. Metric Scaling & Build-Plate Snap    src/loom/scaling/ , scripts/demo.py
    • Primary: ArUco fiducial detection (DICT_5X5_100) + multi-view DLT scale
    • Fallback: Uniform float64 scaling to CLI --target-length (default 200.0 mm)
      in memory prior to STL serialization (prevents float32 quantization collapse)
    • Build-plate snap: Z_min = 0.000000 mm, centered at (X=0, Y=0)
              │
              ▼
 8. Printability Gate & Binary STL       src/loom/printability/gate.py
    Export with Cryptographic Manifest   src/loom/export/stl.py
    • PrintabilityGate enforces: watertight (0 boundary edges), 2-manifold
      (0 non-manifold edges/vertices), consistent outward normals, volume > 0
    • Binary STL export verified against exact byte length 84 + 50 * N_faces
    • Companion JSON build manifest with SHA-256 hash, OBB/AABB dims, scale factor
```

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

---

## 3. Core Geometric & Runtime Invariants

1. **No Camera-Axis Elevation Bias:** Support plane RANSAC runs over the entire point cloud (sampled up to 60,000 points), never slicing by raw camera-frame Z, guaranteeing invariance to arbitrary handheld tilt.
2. **Gravity Polarity Ground Truth:** When `sparse/0/images.bin` camera centers $\mathbf{C}_{\text{cam}}$ are present, the plane normal $\mathbf{n}$ is guaranteed to satisfy $\mathbf{n} \cdot (\mathbf{C}_{\text{cam}} - \mathbf{p}_0) > 0$.
3. **Synchronous Vertex & Normal Rotation:** Poisson reconstruction requires outward-consistent vertex normals `(nx, ny, nz)`. Both vertex coordinates and unit normal vectors rotate synchronously under the same $SO(3)$ matrix $R$.
4. **Closed Poisson Zero-Crossing:** `--PoissonMeshing.trim 0` is locked so Poisson produces a watertight shell prior to controlled planar base slicing at $Z = 0.005$.
5. **SfM Tracking Circuit Breaker:** Sparse mapping aborts immediately with `RuntimeError` if fewer than 75% of input frames register in `images.bin`, preventing downstream starburst artifacts on incomplete orbits.
6. **CUDA Dynamic Linker Isolation:** `src/loom/utils/subprocess.py` automatically prepends `/opt/cuda/lib64` to `LD_LIBRARY_PATH` whenever present on the host so `/usr/bin/colmap` resolves `libcudart.so.*` reliably.
7. **Zero Heavyweight ML Dependencies:** The core pipeline relies strictly on `numpy`, `scipy`, `trimesh`, `mapbox-earcut`, `opencv-python`, `pyyaml`, and native COLMAP 4.2.0 CUDA; `open3d` remains strictly optional.

