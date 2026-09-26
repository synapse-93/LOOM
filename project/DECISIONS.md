# ARCHITECTURE DECISION RECORDS (ADR) — VIDEO2PRINT

This document records the architectural and engineering decisions accepted for VIDEO2PRINT. Every entry follows the ADR specification.

---

## ADR Index

- [ADR-001: Standardization on Python 3.10.11 Runtime](#adr-001-standardization-on-python-31011-runtime)
- [ADR-002: Selection of Meshroom / AliceVision CLI as Initial Reconstruction Backend](#adr-002-selection-of-meshroom--alicevision-cli-as-initial-reconstruction-backend)
- [ADR-003: Subprocess Isolation and Adapter Pattern for External Reconstruction Tools](#adr-003-subprocess-isolation-and-adapter-pattern-for-external-reconstruction-tools)
- [ADR-004: Known-Size Reference Marker (ArUco) for Development Metric Scaling](#adr-004-known-size-reference-marker-aruco-for-development-metric-scaling)
- [ADR-005: Deterministic Optical Quality Assessment and Thumbnail Redundancy Filtering](#adr-005-deterministic-optical-quality-assessment-and-thumbnail-redundancy-filtering)

---

## ADR-001: Standardization on Python 3.10.11 Runtime

- **Status**: ACCEPTED
- **Date**: 2026-09-26
- **Decision**: Adopt Python 3.10.11 as the designated baseline execution environment for the project.
- **Reason**:
  - Python 3.10 provides optimal binary wheel compatibility across critical 3D geometry and computer vision libraries (`open3d`, `pymeshlab`, `trimesh`, `opencv-python`).
  - Newer Python releases (e.g. Python 3.12, 3.13, 3.14) frequently lack pre-compiled wheels for C++-bound geometry tools like `pymeshlab` and `open3d` on Windows.
  - Python 3.10.11 is verified to be installed on the development host system (`py -3.10`).
- **Alternatives Considered**:
  - *Python 3.14 (Default host Python)*: Incompatible; scientific and 3D mesh processing wheels are largely unavailable.
  - *Python 3.8 / 3.9*: Older syntax, end-of-life or approaching end-of-life status.
- **Consequences**:
  - Virtual environments must be created explicitly using `py -3.10 -m venv .venv`.
  - Agents must avoid Python 3.11+ exclusive features (e.g., `except*`, `Self` from typing without typing-extensions).

---

## ADR-002: Selection of Meshroom / AliceVision CLI as Initial Reconstruction Backend

- **Status**: ACCEPTED
- **Date**: 2026-09-26
- **Decision**: Use Meshroom / AliceVision CLI as the primary initial external photogrammetry engine.
- **Reason**:
  - AliceVision provides an open-source, reproducible Structure-from-Motion (SfM) and Multi-View Stereo (MVS) pipeline.
  - Meshroom provides straightforward command-line workflow automation (`meshroom_batch` / individual AliceVision node binaries).
  - It handles feature extraction, camera estimation, depth map generation, and mesh reconstruction without requiring custom SfM implementations.
- **Alternatives Considered**:
  - *Custom SfM/MVS implementation*: Rejected. Writing robust multi-view stereo and bundle adjustment from scratch would consume the entire semester without matching production reliability.
  - *COLMAP + OpenMVS*: Excellent alternative, but Meshroom was chosen as the starting point due to its unified CLI packaging. COLMAP will be supported as a subsequent interchangeable backend.
  - *NeRF / 3D Gaussian Splatting*: Premature and non-standard for CAD/3D printing. Meshing from radiance fields remains noisy and lacks geometric/metric precision compared to classical MVS.
- **Consequences**:
  - Dense depth mapping requires an NVIDIA GPU with CUDA.
  - The software must be installed as an external tool, and the pipeline must handle cases where the tool is missing or fails.

---

## ADR-003: Subprocess Isolation and Adapter Pattern for External Reconstruction Tools

- **Status**: ACCEPTED
- **Date**: 2026-09-26
- **Decision**: Isolate all external reconstruction binaries behind an abstract `ReconstructionEngine` interface invoked exclusively through managed subprocesses.
- **Reason**:
  - Prevents tight coupling between the core VIDEO2PRINT application and external toolchain quirks.
  - Enables switching or adding backends (e.g. COLMAP, OpenMVS) with zero modifications to upstream frame selection or downstream mesh cleaning, scaling, and validation.
  - Subprocess isolation protects the Python runtime from C++ native crashes or memory leaks in photogrammetry engines.
- **Alternatives Considered**:
  - *Direct Python C-bindings (e.g., pycolmap)*: Introduces delicate compilation dependencies and platform-specific build issues on Windows.
  - *Hardcoding Meshroom file structures into the core pipeline*: Severely violates modularity and makes backend switching nearly impossible.
- **Consequences**:
  - Data transfer occurs via filesystem artifacts (directories of images, `.obj` / `.ply` files).
  - Overhead of process launching and file I/O is negligible compared to photogrammetry computation time.

---

## ADR-004: Known-Size Reference Marker (ArUco) for Development Metric Scaling

- **Status**: ACCEPTED
- **Date**: 2026-09-26
- **Decision**: Use a known-size physical fiducial marker (ArUco marker or ArUco grid board) placed beside or beneath the target object to establish absolute metric scale.
- **Reason**:
  - Monocular Structure-from-Motion has intrinsic gauge freedom (scale ambiguity); absolute real-world size cannot be determined from uncalibrated 2D video frames alone.
  - ArUco markers can be detected with sub-pixel corner accuracy using `opencv-python`.
  - Calculating scale from known millimeter marker dimensions ($s = \frac{d_{\text{physical}}}{d_{\text{reconstructed}}}$) is deterministic, verifiable, and does not require active depth sensors (LiDAR/ToF).
- **Alternatives Considered**:
  - *Smartphone LiDAR / ARKit / ARCore scale*: Device-dependent (requires high-end iPhone Pro or specific Android phones) and limits accessibility.
  - *Manual scale factor input*: Subjective, error-prone, and fails the requirement for automated manufacturing readiness.
  - *Object-bounding-box prior*: Unreliable for arbitrary organic or unfamiliar mechanical shapes.
- **Consequences**:
  - Capture protocol during development requires the user to place an ArUco marker in the scene alongside the target object.
  - The marker geometry must later be segmented out or trimmed from the final printable object mesh if it contacts the object.

---

## ADR-005: Deterministic Optical Quality Assessment and Thumbnail Redundancy Filtering

- **Status**: ACCEPTED
- **Date**: 2026-09-26
- **Decision**: Adopt Laplacian variance for blur detection, grayscale mean/standard deviation for exposure/contrast validation, and 64x64 grayscale thumbnail mean absolute difference for inter-frame redundancy filtering.
- **Reason**:
  - Computational efficiency: These metrics require basic matrix operations via NumPy and OpenCV, executing in milliseconds per frame without GPU requirements or neural network dependencies.
  - Determinism: Given identical frame input, the quality scoring and accept/reject decisions are 100% reproducible.
  - Redundancy filtering prevents feeding hundreds of static or near-static consecutive frames into photogrammetry, which would explode bundle adjustment computation time without increasing geometric reconstruction quality.
  - A 64x64 normalized thumbnail captures overall scene composition and viewpoint shifts while being insensitive to high-frequency sensor noise.
- **Alternatives Considered**:
  - *Optical Flow (Lucas-Kanade / Farneback)*: Accurate but substantially slower for long 4K/1080p video sequences. Deferred to later optimization phases if simple difference metrics prove insufficient on difficult footage.
  - *Deep learning quality models (e.g., BRISQUE, KonIQ, NIMA)*: Heavyweight dependencies (PyTorch/TensorFlow) violating Phase 1 dependency rules, non-deterministic across devices, and unnecessary for basic blur/exposure gating.
- **Consequences**:
  - Default thresholds (`sharpness_threshold=100.0`, `min_brightness=30.0`, `max_brightness=235.0`, `min_contrast=15.0`, `redundancy_threshold=0.98`) provide robust initial filtering but remain fully user-configurable via `CaptureConfig` for challenging lighting environments.
