# Phase 2 — Multi-View 3D Reconstruction Architecture & Specification

## 1. Executive Summary & Status Boundary

Phase 2 takes selected, high-quality keyframes from Phase 1 and passes them to an interchangeable 3D photogrammetry backend to produce camera registrations, sparse/dense point clouds, raw surface meshes, and reconstruction diagnostics.

> [!IMPORTANT]
> **Definitive Status Boundary**:
> - **Software Architecture & Contracts**: COMPLETE
> - **Backend Adapter (`MeshroomAdapter`)**: IMPLEMENTED & HARDENED
> - **Automated Unit & Integration Tests**: VERIFIED (75 passing tests, mocked subprocesses)
> - **Live Physical Reconstruction**: **BLOCKED / NOT YET VALIDATED**
> 
> Neither `meshroom_batch` nor `colmap` is currently installed on the development host (`ISSUE-BLK-002`). Zero live reconstruction runs on physical objects have been performed. No point counts, registration percentages, or accuracy tolerances may be claimed until live physical benchmarks are executed.

---

## 2. Pipeline Sequence & Conceptual Stages

Reconstruction follows an 8-stage conceptual sequence defined in `ReconstructionStage`:

```
PHASE 1 OUTPUT (Selected Keyframes)
                 │
                 ▼
┌───────────────────────────────────────────────┐
│ Stage 0: Input Validation                     │  Verify frame list non-empty, files exist, formats supported
├───────────────────────────────────────────────┤
│ Stage 1: Camera Init & Feature Matching       │  Extract keypoints (SIFT), match feature pairs
├───────────────────────────────────────────────┤
│ Stage 2: Camera Registration / SfM            │  Estimate extrinsic camera poses and focal parameters
├───────────────────────────────────────────────┤
│ Stage 3: Sparse Reconstruction                │  Triangulate 3D tie points (sparse point cloud)
├───────────────────────────────────────────────┤
│ Stage 4: Dense Reconstruction (MVS)           │  Multi-view stereo depth map fusion (dense point cloud)
├───────────────────────────────────────────────┤
│ Stage 5: Raw Surface / Mesh Generation        │  Initial surface extraction (Delaunay/Meshing) -> OBJ
├───────────────────────────────────────────────┤
│ Stage 6: Artifact Discovery                   │  Scan workspace for meshes, dense/sparse clouds, poses
├───────────────────────────────────────────────┤
│ Stage 7: Diagnostics & Report Generation      │  Compute registration ratio, log parsing, write JSON
└───────────────────────────────────────────────┘
                 │
                 ▼
PHASE 2 OUTPUT (ReconstructionResult -> reports/reconstruction.json)
                 │
                 ▼
PHASE 3 (Raw Geometry Processing & Mesh Cleanup)
```

---

## 3. Strict Boundary & Non-Goals

Phase 2 is strictly bounded to raw multi-view photogrammetry. It **MUST NOT** perform:
- Mesh hole repair, topological manifold checks, or surface smoothing (reserved for **Phase 3**).
- Watertight volume generation or Poisson remeshing (reserved for **Phase 3**).
- Physical metric scaling or ArUco reference marker detection (reserved for **Phase 4**).
- Dimensional accuracy evaluation or CAD ground-truth deviation (reserved for **Phase 5**).
- Slicing, overhang detection, or printability validation (reserved for **Phase 6**).
- Final binary STL export (reserved for **Phase 7**).
- NeRF, 3D Gaussian Splatting, Depth Anything, or PyTorch neural estimation (prohibited by `.agents/rules/python.md` and `.agents/rules/architecture.md`).

---

## 4. Subsystem Contracts

### 4.1 Backend Engine Interface (`ReconstructionEngine`)

All reconstruction backends inherit from the abstract base class `ReconstructionEngine` (`src/loom/reconstruction/base.py`):

```python
class ReconstructionEngine(ABC):
    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Identifier for the engine backend (e.g. 'meshroom', 'colmap')."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether required backend executables exist on host PATH or configured location."""
        ...

    @abstractmethod
    def reconstruct(
        self,
        frame_paths: Sequence[Path],
        config: ReconstructionJobConfig,
    ) -> ReconstructionResult:
        """Execute reconstruction pipeline on input keyframes."""
        ...
```

### 4.2 Input Configuration (`ReconstructionJobConfig`)

```python
@dataclass(frozen=True)
class ReconstructionJobConfig:
    workspace_dir: Path
    quality_preset: str = "medium"
    timeout_seconds: int = 1800
    camera_model: str = "pinhole"
    binary_path: Optional[Path] = None
    keep_workspace: bool = True
    additional_args: list[str] = field(default_factory=list)
    extra_params: dict[str, str] = field(default_factory=dict)
```

### 4.3 Output Result (`ReconstructionResult`)

Outputs are strictly typed. Unavailable measurements remain `None` rather than fabricated values:

```python
@dataclass(frozen=True)
class ReconstructionResult:
    success: bool = False
    status: ReconstructionStatus = ReconstructionStatus.SUCCESS
    backend_name: str = "unknown"
    mesh_path: Optional[Path] = None
    sparse_reconstruction_path: Optional[Path] = None
    dense_point_cloud_path: Optional[Path] = None
    point_cloud_path: Optional[Path] = None
    camera_poses_path: Optional[Path] = None
    registered_cameras_count: Optional[int] = None
    input_frames_count: int = 0
    registration_ratio: Optional[float] = None
    point_count: Optional[int] = None
    execution_time_seconds: float = 0.0
    workspace_dir: Optional[Path] = None
    log_path: Optional[Path] = None
    error_message: Optional[str] = None
```

---

## 5. Failure Classification

Failures are explicitly categorized via `ReconstructionStatus` (`src/loom/reconstruction/models.py`) and dedicated exceptions:

| Status (`ReconstructionStatus`) | Exception | Description |
| :--- | :--- | :--- |
| `SUCCESS` | *None* | Subprocess completed (exit 0), raw 3D mesh (`.obj`) generated and validated non-empty. |
| `PARTIAL` | `ReconstructionPartialError` | Subprocess completed (exit 0), sparse/dense point cloud or camera poses generated, but mesh missing. |
| `BINARY_UNAVAILABLE` | `ReconstructionBinaryNotFoundError` | Engine executable (`meshroom_batch`) not found on PATH or configured path. Gracefully detected. |
| `INVALID_INPUT` | `ReconstructionInvalidInputError` | Frame list is empty, contains non-existent files, or unsupported image formats. |
| `PROCESS_FAILED` | `ReconstructionExecutionError` | Subprocess exited with a non-zero exit code. Detailed stderr/stdout recorded in log. |
| `TIMEOUT` | `ReconstructionTimeoutError` | Subprocess execution exceeded `timeout_seconds`. Process terminated cleanly. |
| `ARTIFACT_MISSING` | `ReconstructionArtifactNotFoundError` | Subprocess exited with 0 but zero expected artifacts (point clouds, poses, or mesh) were generated. |

---

## 6. Meshroom Adapter Implementation

`MeshroomAdapter` (`src/loom/reconstruction/meshroom.py`) provides the reference AliceVision implementation:

1. **Subprocess Isolation**: Uses `subprocess.Popen` with argument lists (never `shell=True`) to prevent shell injection.
2. **Deterministic Workspace Layout**:
   - `input/`: Symlinks or copies of selected keyframes.
   - `output/`: Direct target for AliceVision node outputs.
   - `cache/`: Intermediate AliceVision pipeline node cache.
   - `logs/reconstruction.log`: Complete stdout and stderr captured in real time.
3. **Artifact Discovery**:
   - Primary Mesh: `texturedMesh.obj`, `mesh.obj`.
   - Dense Cloud: `densePointCloud.ply`, `pointCloud.ply`.
   - Sparse Cloud: `cloud_and_poses.ply`, `sfm.ply`.
   - Camera Poses: `cameras.sfm`.
4. **Metadata Parsing**: Safely parses `cameras.sfm` JSON to count registered camera poses and calculate registration ratio without external dependencies.

---

## 7. Standardized Report Schema (`reconstruction.json`)

Written to `outputs/runs/<run_id>/reports/reconstruction.json`:

```json
{
  "run_id": "run_20260926_195429_synthetic_test",
  "timestamp": "2026-09-26T14:24:31.035843+00:00",
  "backend": "meshroom",
  "status": "binary_unavailable",
  "success": false,
  "input_frames": 5,
  "registered_cameras": null,
  "registration_ratio": null,
  "point_count": null,
  "sparse_reconstruction": null,
  "point_cloud_path": null,
  "dense_point_cloud_path": null,
  "camera_poses_path": null,
  "mesh_generated": false,
  "mesh_path": null,
  "execution_time_seconds": 0.0,
  "workspace_path": "C:\\Users\\...\\reconstruction",
  "workspace_dir": "C:\\Users\\...\\reconstruction",
  "log_path": null,
  "error_message": "Reconstruction backend 'meshroom' executable not found. Ensure Meshroom is installed or configure 'binary_path'."
}
```

---

## 8. Verification & Test Strategy

Phase 2 is validated through 75 passing unit and integration tests covering:
- Factory engine resolution and unknown backend rejection.
- Binary detection and graceful failure when absent.
- Input validation (empty lists, non-existent paths, invalid extensions).
- Command line construction and parameter mapping.
- Subprocess execution and real-time log streaming.
- Subprocess non-zero exit code error handling.
- Timeout triggering and process tree cleanup.
- SFM JSON parsing (valid, corrupt, and missing).
- Output artifact discovery with sparse/dense separation.
- Mocked end-to-end reconstruction producing valid OBJ meshes.
- Mocked partial reconstruction (clouds/poses without mesh).
- Mocked missing artifacts when process exits 0.
- End-to-end integration with Phase 1 pipeline runner with graceful degradation.
- CLI argument parsing (`--reconstruct`, `--meshroom-path`).
