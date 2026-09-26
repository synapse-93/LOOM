# 3D RECONSTRUCTION SUBSYSTEM RULES — VIDEO2PRINT

**Scope**: Rules, constraints, and interface specifications for 3D reconstruction backends in VIDEO2PRINT.

---

## 1. External Backend Strategy

1. **Subprocess Isolation**:
   - 3D photogrammetry engines (Structure-from-Motion / Multi-View Stereo) are mature, compute-intensive standalone tools.
   - VIDEO2PRINT does not re-implement SfM/MVS algorithms in native Python.
   - Engines such as **Meshroom / AliceVision** (and future alternatives like **COLMAP / OpenMVS**) are treated strictly as external backends invoked via subprocesses.
2. **Adapter Decoupling**:
   - All interactions with reconstruction software must occur through concrete implementations of `ReconstructionEngine`.
   - The core pipeline must have zero knowledge of Meshroom graph files (`.mg`), internal node IDs, or proprietary pipeline topologies.
   - Swapping the backend from Meshroom to COLMAP must only require writing a new adapter without altering downstream mesh processing, scaling, validation, or printability stages.
3. **Execution Robustness**:
   - Subprocess invocations must specify explicit timeouts, capture `stdout` and `stderr` streams, log return codes, and inspect generated files.
   - Temporary working directories for external tools must be organized under dedicated, ignorable scratch paths.

---

## 2. Inherent Scale Ambiguity in Monocular Reconstruction

1. **Fundamental CV Reality**:
   - Monocular camera video reconstruction (uncalibrated or auto-calibrated single-camera SfM) suffers from **inherent gauge freedom and scale ambiguity**.
   - The reconstructed point cloud and mesh coordinates are dimensionless relative units ($s \cdot \mathbf{X}$ where $s$ is an unknown positive scalar).
   - Monocular SfM cannot determine whether an object is a 20 mm miniature toy or a 20 meter physical structure without an external metric reference.
2. **Development Metric Scaling Strategy**:
   - For development and validation, a **known-size physical reference target** must be present in the capture scene.
   - Primary approach: Calibrated **ArUco fiducial marker** or ArUco grid board of known physical millimeter dimensions (e.g. $50.0\text{ mm} \times 50.0\text{ mm}$).
   - Secondary approach: A calibrated 3D geometric gauge block / coin of certified dimensions.
   - The metric scaling subsystem identifies this reference, recovers the scale factor $s = \frac{d_{\text{physical}}}{d_{\text{reconstructed}}}$, and scales the mesh uniformly into millimeters.

---

## 3. Data Contracts & Artifact Standards

1. **Input Contract**:
   - Directory containing undistorted or sequential RGB keyframes (`.png` or high-quality `.jpg`).
   - Optional camera calibration parameters (focal length, principal point) if pre-calibrated.
2. **Output Contract**:
   - Output directory containing:
     - Reconstructed 3D mesh: Standard Wavefront (`.obj`) or Polygon File Format (`.ply`).
     - Reconstructed dense point cloud (`.ply`) if available.
     - Camera trajectories / poses if supported by backend.
     - Execution logs and timing statistics.
3. **Failure Handling**:
   - If feature matching fails, insufficient cameras are registered, or depth reconstruction generates an empty mesh, the adapter must raise `ReconstructionError` with diagnostic context rather than returning corrupt or empty files.

---

## 4. Hardware Realities & Graceful Degradation

- AliceVision / Meshroom dense depth map estimation (DepthMap node) typically requires an NVIDIA GPU with CUDA compute capability.
- In environments lacking NVIDIA GPUs or external tool binaries:
  - Adapters must provide an `.is_available()` check.
  - Tests must provide mock/synthetic fixtures to allow geometric testing without executing live photogrammetry.
  - The pipeline must clearly report missing binaries rather than crashing with unhandled OS errors.
