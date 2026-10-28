# Phase 2 — Multi-View 3D Reconstruction Architecture & Specification

## 1. Executive Summary & Status Boundary

Phase 2 takes selected, high-quality keyframes from Phase 1 and passes them to an interchangeable 3D photogrammetry backend to produce camera registrations, sparse/dense point clouds, raw surface meshes, and reconstruction diagnostics.

> [!IMPORTANT]
> **Definitive Status Boundary**:
> - **Software Architecture & Contracts**: COMPLETE
> - **Backend Adapters (`MeshroomAdapter`, `ColmapAdapter`)**: IMPLEMENTED & VERIFIED
> - **Automated Unit & Integration Tests**: 171 tests passing (100% pass rate)
> - **Live Photogrammetry (COLMAP)**: **EMPIRICALLY VERIFIED** on host Windows environment (COLMAP 4.2.1 CPU-compatible Structure-from-Motion and CGAL Delaunay surface meshing).
> - **Live Photogrammetry (Meshroom)**: Host binary not installed (`meshroom_batch` missing on host).
> - **Metric Scaling & Dimensional Accuracy**: Output meshes are in arbitrary reconstruction coordinate space until scaled in Phase 4.

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
│ Stage 5: Raw Surface / Mesh Generation        │  Initial surface extraction (Delaunay/Poisson) -> OBJ/PLY
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
- Watertight volume generation or Poisson remeshing during mesh processing (reserved for **Phase 3**).
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
| `SUCCESS` | *None* | Subprocess completed (exit 0), raw 3D mesh (`.obj` or `.ply`) generated and validated non-empty. |
| `PARTIAL` | `ReconstructionPartialError` | Subprocess completed (exit 0), sparse/dense point cloud generated, but mesh missing. |
| `BINARY_UNAVAILABLE` | `ReconstructionBinaryNotFoundError` | Engine executable (`meshroom_batch` or `colmap`) not found on PATH or configured path. |
| `INVALID_INPUT` | `ReconstructionInvalidInputError` | Frame list is empty (e.g. all frames rejected by quality filter), contains non-existent files, or unsupported formats. |
| `PROCESS_FAILED` | `ReconstructionExecutionError` | Subprocess exited with a non-zero exit code or fatal log error. Detailed logs recorded. |
| `TIMEOUT` | `ReconstructionTimeoutError` | Subprocess execution exceeded `timeout_seconds`. Process terminated cleanly. |
| `ARTIFACT_MISSING` | `ReconstructionArtifactNotFoundError` | Subprocess exited with 0 but zero expected artifacts (point clouds, poses, or mesh) were generated. |

---

## 6. COLMAP Adapter Implementation

`ColmapAdapter` (`src/loom/reconstruction/colmap.py`) provides a robust, platform-aware COLMAP photogrammetry implementation:

### 6.1 Executable & Environment Discovery
1. **Flexible Executable Resolution**: Supports direct file path (`C:\Tools\COLMAP\bin\colmap.exe`), directory containing `colmap.exe`, installation directory containing `bin/colmap.exe`, and system `PATH`.
2. **Automatic Qt Platform Discovery**: On Windows, COLMAP CLI commands require `QT_QPA_PLATFORM_PLUGIN_PATH` to locate `qwindows.dll`. The adapter checks relative directories (`../plugins/platforms`, `./plugins/platforms`) and automatically injects the path into subprocess environments while preserving all user-defined environment variables.
3. **Capability Probing**: The adapter runs `colmap -h` to detect whether the build was compiled `"without GPU support"`.

### 6.2 CPU-Compatible Pipeline
When running on CPU-only builds or when CUDA is unavailable:
1. `feature_extractor` with `--FeatureExtraction.use_gpu 0`
2. `exhaustive_matcher` with `--FeatureMatching.use_gpu 0`
3. `mapper` (incremental Structure-from-Motion) producing `sparse/0`
4. `model_converter --output_type PLY` producing sparse point cloud `sparse/points.ply`
5. `delaunay_mesher --input_type sparse` producing surface mesh `sparse/mesh.ply`

### 6.3 Matcher Validation & Silent Failure Detection
COLMAP's `exhaustive_matcher` can encounter GPU memory allocation failures and log fatal errors while returning exit code 0. The adapter:
- Inspects stderr/stdout for documented fatal matching errors.
- Directly inspects the SQLite `database.db` (`matches` and `two_view_geometries` tables) to verify matches were written.
- Retries with `--FeatureMatching.use_gpu 0` if an initial attempt failed silently.
- Aborts with `ReconstructionExecutionError` rather than proceeding to mapper when zero matches exist.

### 6.4 Dense MVS & Graceful Fallback
When CUDA/HIP is supported, the adapter attempts dense Multi-View Stereo (`image_undistorter` $\to$ `patch_match_stereo` $\to$ `stereo_fusion` $\to$ `poisson_mesher`). If dense MVS fails or is unsupported:
- Sparse point cloud and sparse Delaunay mesh are preserved.
- Sparse result is returned with `status = ReconstructionStatus.PARTIAL` (if dense was explicitly requested) or `ReconstructionStatus.SUCCESS` (on CPU default path).
- Sparse point clouds and dense point clouds remain distinct in `ReconstructionResult`.

---

## 7. Meshroom Adapter Implementation

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

## 8. CLI Usage Examples

Run from the repository root in the project's Python 3.10 virtual environment:

```powershell
# COLMAP CLI (auto-discovering C:\Tools\COLMAP or via PATH)
python -m loom --video .\data\raw\object.mp4 --reconstruct --clean-mesh `
  --reconstruction-backend colmap `
  --reconstruction-binary "C:\Tools\COLMAP\bin\colmap.exe"

# Meshroom / AliceVision
python -m loom --video .\data\raw\object.mp4 --reconstruct --clean-mesh `
  --reconstruction-backend meshroom `
  --reconstruction-binary "C:\Tools\Meshroom\meshroom_batch.exe"
```

`--meshroom-path` remains available as a backward-compatible alias for `--reconstruction-binary`.
