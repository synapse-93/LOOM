# ARCHITECTURE RULES — VIDEO2PRINT

**Scope**: System design, component boundaries, and interface contracts for VIDEO2PRINT.

---

## 1. Core Architectural Principles

1. **Strict Modularity**: Each stage in the pipeline is a self-contained module with defined inputs, outputs, and configuration. Modules must never bypass standard interfaces or mutate inputs unpredictably.
2. **Subsystem Isolation**: External reconstruction binaries (Meshroom, AliceVision, COLMAP) run in separate processes and are accessed exclusively through an abstract adapter interface.
3. **Reproducibility by Design**: Every pipeline execution receives an explicit configuration object and logs all parameters, input hashes, intermediate artifacts, and output metrics.
4. **Independent Testability**: Every stage must be testable in isolation using synthetic fixtures or saved intermediate artifacts (e.g. extracted frames, raw meshes, point clouds).
5. **No Premature Complexity**: Keep initial implementations focused on classical computer vision and solid computational geometry. Do not introduce microservices, distributed queues, heavy deep-learning frameworks, or web frontends until required and formally decided.

---

## 2. Pipeline Stages & Responsibilities

The pipeline follows a linear, staged flow where each stage consumes artifacts from preceding stages:

```
[ Smartphone Video ]
         │
         ▼
 1. Video Processing      (video/)          ──> Validated frame sequence & metadata
         │
         ▼
 2. Frame Selection       (frames/)         ──> Filtered, sharp, high-overlap keyframes
         │
         ▼
 3. Reconstruction Engine (reconstruction/) ──> Raw 3D point cloud / triangle mesh (arbitrary scale)
         │
         ▼
 4. Mesh Processing       (mesh/)           ──> Cleaned, manifold surface representation
         │
         ▼
 5. Metric Scaling        (scaling/)        ──> Physically scaled 3D mesh (in millimeters)
         │
         ▼
 6. Geometry Validation   (validation/)     ──> Dimensional error metrics vs ground truth
         │
         ▼
 7. Printability Analysis (printability/)   ──> Watertightness, wall thickness, overhang report
         │
         ▼
 8. Model Export          (export/)         ──> Final manufacturing-ready STL & build metadata
```

### Stage 1: Video Processing (`src/loom/video/`)
- **Responsibility**: Ingest video files (`.mp4`, `.mov`), extract frame streams, decode timestamps, camera metadata (if available), and validate video integrity.
- **Contract**: Accepts a video path; outputs a sequence of extracted image frames with an extraction manifest (index, timestamp, resolution).

### Stage 2: Frame Selection & Quality Assessment (`src/loom/capture/`)
- **Responsibility**: Assess per-frame sharpness (e.g. Laplacian variance), motion blur, lighting/exposure, and inter-frame visual overlap.
- **Contract**: Accepts extracted frames; outputs a selected subset of optimal keyframes suitable for Structure-from-Motion (SfM), rejecting blurry or redundant frames.

### Stage 3: 3D Reconstruction Backend (`src/loom/reconstruction/`)
- **Responsibility**: Interface with external photogrammetry / SfM / MVS software.
- **Contract**: Accepts a directory of selected keyframes; produces a raw 3D mesh (`.obj` or `.ply`) and camera poses.
- **Replaceability**: Must implement the `ReconstructionEngine` abstract base class. Core pipeline code must never depend on Meshroom or COLMAP directly.

### Stage 4: Mesh Processing & Cleanup (`src/loom/mesh/`)
- **Responsibility**: Ingest raw reconstruction output; perform outlier removal, noise filtering, surface reconstruction (e.g. Screened Poisson), hole filling, and non-manifold element removal.
- **Contract**: Accepts a raw mesh / point cloud; outputs a topologically clean surface mesh.

### Stage 5: Metric Scaling Subsystem (`src/loom/scaling/`)
- **Responsibility**: Monocular SfM output has an arbitrary scale factor. This stage detects a physical reference target (e.g. ArUco marker / calibration target) in the capture images or point cloud to compute the metric conversion factor.
- **Contract**: Accepts a cleaned mesh and reference detection data; outputs a scaled mesh transformed into physical units (millimeters: $1.0\text{ unit} = 1.0\text{ mm}$).

### Stage 6: Geometry Validation (`src/loom/validation/`)
- **Responsibility**: Measure dimensions, compute bounding boxes, and quantitatively compare reconstructed geometry against known physical ground truth or reference CAD models.
- **Contract**: Accepts scaled mesh and ground truth parameters; produces a structured validation report (absolute error, relative error, Hausdorff distance).

### Stage 7: Printability Analysis (`printability/`)
- **Responsibility**: Verify 3D print readiness:
  - 2-manifold verification (no non-manifold edges or vertices)
  - Watertightness (volume is fully enclosed with no holes or unclosed boundaries)
  - Normal consistency (all outward-facing normals)
  - Minimum wall thickness evaluation
  - Overhang angle analysis (against standard $45^\circ$ FDM limits)
- **Contract**: Accepts scaled mesh; outputs a pass/fail printability report with detected defect coordinates.

### Stage 8: Model Export (`export/`)
- **Responsibility**: Generate standard manufacturing files (binary STL), orientation metadata, and job summary reports.
- **Contract**: Accepts a validated, printable mesh; writes final `.stl` artifact and a machine-readable JSON manifest.

---

## 3. Replaceable Reconstruction Interface Pattern

To guarantee interchangeable reconstruction backends, all photogrammetry engines must adhere to a strict interface:

```python
from abc import ABC, abstractmethod
from pathlib import Path
from dataclasses import dataclass

@dataclass(frozen=True)
class ReconstructionConfig:
    workspace_dir: Path
    quality_preset: str = "medium"
    timeout_seconds: int = 1800

@dataclass(frozen=True)
class ReconstructionResult:
    mesh_path: Path
    point_cloud_path: Path | None
    camera_poses_path: Path | None
    success: bool
    execution_time_seconds: float
    log_output: str

class ReconstructionEngine(ABC):
    @abstractmethod
    def is_available(self) -> bool:
        """Check if external binaries/dependencies exist and are executable."""
        ...

    @abstractmethod
    def reconstruct(self, frame_dir: Path, config: ReconstructionConfig) -> ReconstructionResult:
        """Execute reconstruction pipeline on input frames."""
        ...
```

Concrete implementations (e.g., `MeshroomAdapter`, `ColmapAdapter`) implement this interface. The pipeline coordinator interacts only with `ReconstructionEngine`.

---

## 4. Architectural Boundaries & Anti-Patterns

- **NEVER** import reconstruction-specific libraries (e.g. AliceVision node definitions) into geometry or validation modules.
- **NEVER** use global mutable state or module-level singletons for pipeline state.
- **NEVER** pass file paths as raw unstructured strings; use `pathlib.Path`.
- **NEVER** perform deep-learning inference or import PyTorch/TensorFlow without prior ADR approval.
