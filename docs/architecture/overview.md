# LOOM Architecture Overview

**LOOM** (VIDEO2PRINT) is an engineering and research system that transforms ordinary consumer smartphone video of physical objects into metrically scaled, geometrically validated, and 3D printable objects (.STL).

---

## Staged Pipeline Architecture

The pipeline executes as a sequential chain of decoupled stages:

```
[ Smartphone Video (.mp4 / .mov) ]
              │
              ▼
1. Video Ingest & Extraction (loom.video)
   - Streamed frame extraction without memory bloat
   - Container validation and metadata parsing
              │
              ▼
2. Capture Quality & Guidance (loom.capture)
   - Sharpness scoring (Laplacian variance) & motion blur rejection
   - Viewpoint coverage estimation across orbit
              │
              ▼
3. 3D Reconstruction Engine (loom.reconstruction)
   - Abstract adapter layer (ReconstructionEngine)
   - External photogrammetry tools (Meshroom / AliceVision, COLMAP)
   - Subprocess isolation with timeout and resource tracking
              │
              ▼
4. Point Cloud Processing (loom.pointcloud)
   - Statistical outlier removal and voxel downsampling
   - Spatial density analysis
              │
              ▼
5. Mesh Processing & Surface Reconstruction (loom.mesh)
   - Disconnected component filtering
   - Surface hole filling and normal unification
   - Poisson / Ball Pivoting surface reconstruction
              │
              ▼
6. Metric Scaling Subsystem (loom.scaling)
   - Scale recovery from physical reference markers (ArUco)
   - Scale factor computation (physical mm / reconstructed unit)
   - Mesh coordinate transformation into real-world millimeters
              │
              ▼
7. Geometry Validation (loom.validation)
   - Quantitative dimensional measurement
   - Error comparison against physical ground truth (calipers / CAD)
   - Hausdorff distance and surface deviation
              │
              ▼
8. Printability Analysis (loom.printability)
   - 2-manifold surface verification
   - Watertightness (closed volume) verification
   - Wall thickness estimation and overhang analysis (>45 deg)
              │
              ▼
9. Manufacturing Export (loom.export)
   - Binary STL export
   - Build manifest with cryptographic hashes, volume, and dimensions
   - Print job summary report
```

---

## Key Design Principles

1. **Replaceable Reconstruction Backends**:
   - Photogrammetry engines are treated strictly as external black-box backends behind the `ReconstructionEngine` interface.
   - The application does not depend on internal Meshroom graph representations or COLMAP SQLite databases.
   - Switching from Meshroom to COLMAP or another photogrammetry engine requires zero alterations to downstream mesh, scaling, validation, or printability modules.

2. **Decoupled Artifact Contracts**:
   - Every stage communicates exclusively through immutable, typed artifact objects (`BaseArtifact` subclasses).
   - Stages do not pass ad-hoc dictionaries or shared global state.

3. **Incremental Implementation**:
   - Modules are scaffolded with explicit contracts.
   - Functionality is implemented phase-by-phase according to [`project/ROADMAP.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/ROADMAP.md).
