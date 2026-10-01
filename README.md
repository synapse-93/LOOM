# LOOM: VIDEO2PRINT

**Smartphone Video → Metrically Scaled → Validated → 3D Printable Object**

LOOM is an engineering and research pipeline that transforms consumer smartphone video of physical objects into metrically scaled, geometrically validated, and 3D printable objects (.STL).

---

## Current Architecture & Implementation Status

The project strictly distinguishes between **Implemented**, **Scaffolded**, and **Planned** functionality:

| Component / Subsystem | Module Path | Status | Description |
| :--- | :--- | :--- | :--- |
| **Package Scaffold & CLI** | `src/loom/` | **Implemented** | Standard src-layout, `python -m loom` entrypoint, logging, paths, subprocess, hashing. |
| **Configuration System** | `src/loom/config/` | **Implemented** | Typed dataclasses, YAML loader, default/dev/experiment presets in `configs/`. |
| **Pipeline Runner & Artifacts** | `src/loom/pipeline/` | **Implemented** | Immutable typed artifact models, `PipelineStage` abstraction, and Phase 1 pipeline runner. |
| **Video Ingest & Frames** | `src/loom/video/` | **Implemented** | Video container validation, stream metadata extraction, streaming frame extraction & manifest. |
| **Capture Quality & Coverage** | `src/loom/capture/` | **Implemented** | Laplacian sharpness, exposure/contrast gating, thumbnail redundancy filter, and capture guidance. |
| **Geometry Utilities** | `src/loom/geometry/` | **Implemented** | 3D coordinate primitives, vector math, bounding box calculation, 4x4 transform matrices. |
| **Mesh Processing & Cleanup** | `src/loom/mesh/` | **Implemented** | Read-only diagnostics, component filtering, invalid geometry cleanup, conservative defect repair, outward normal unification (`--mesh`, `geometry`). |
| **Test Suite** | `tests/` | **Implemented** | 115 automated unit/integration tests verifying ingest, frames, quality, Meshroom adapter, mesh processing, and pipelines. |
| **Diagnostics & Tools** | `scripts/` | **Implemented** | `environment_check.py`, `generate_test_video.py`, and `reconstruction_smoke_test.py`. |
| **3D Reconstruction Engine** | `src/loom/reconstruction/` | **Implemented** | `MeshroomAdapter` subprocess execution, timeout handling, 7-state failure classification, `cameras.sfm` registration metrics, artifact discovery (`--reconstruct`). Live execution blocked pending host binary installation. |
| **Point Cloud Processing** | `src/loom/pointcloud/` | *Scaffolded* | Outlier removal, voxel downsampling interfaces defined. |
| **Metric Scaling Subsystem** | `src/loom/scaling/` | *Scaffolded* | ArUco detection, calibration, and transform interfaces defined; planned for Phase 4. |
| **Geometry Validation** | `src/loom/validation/` | *Scaffolded* | Error models, dimension measurement, JSON report generation defined; planned for Phase 5. |
| **Printability Analysis** | `src/loom/printability/` | *Scaffolded* | Manifold, watertight, thickness, overhang checks defined; planned for Phase 6. |
| **Manufacturing Export** | `src/loom/export/` | *Scaffolded* | Binary STL export, cryptographic manifest, and summary report generator defined; planned for Phase 7. |


---

## Directory Layout

```
LOOM/
├── .agents/                    # Agent constitution, operating rules & guidelines
│   └── rules/
├── configs/                    # Validated YAML configurations
│   ├── default.yaml            # Baseline production configuration
│   ├── development.yaml        # Fast local iteration settings
│   └── experiment.yaml         # High-precision benchmark settings
├── data/                       # Ingest & intermediate data storage (git-ignored)
│   ├── raw/                    # Raw input smartphone video files
│   ├── intermediate/           # Extracted keyframes & temporary assets
│   └── processed/              # Processed datasets
├── docs/                       # Architecture diagrams and technical notes
│   ├── architecture/
│   ├── demo/
│   └── experiments/
├── outputs/                    # Pipeline outputs (git-ignored)
│   ├── reconstructions/        # Raw photogrammetry outputs
│   ├── meshes/                 # Cleaned and scaled meshes
│   ├── stl/                    # Final manufacturing-ready STL models
│   └── reports/                # Validation and printability reports
├── project/                    # Project memory and management system
│   ├── CHANGELOG.md            # Chronological iteration log
│   ├── CONTEXT.md              # Current project state snapshot (read first)
│   ├── DECISIONS.md            # Architecture Decision Records (ADR-001 to ADR-004)
│   ├── EXPERIMENTS.md          # Empirical experiment logs
│   ├── ISSUES.md               # Blockers, limitations, and technical debt
│   └── ROADMAP.md              # Staged 11-phase development roadmap
├── scripts/                    # Diagnostic and utility scripts
│   ├── benchmark.py            # Benchmark execution script (scaffold)
│   ├── environment_check.py    # Python runtime and toolchain diagnostic
│   ├── generate_marker.py      # ArUco marker generator (scaffold)
│   └── generate_test_video.py  # Test video generator (scaffold)
├── src/loom/                   # Core application source package
│   ├── capture/                # Quality and coverage guidance
│   ├── config/                 # Typed configuration models and YAML loader
│   ├── export/                 # STL export and build manifests
│   ├── geometry/               # 3D math and bounding box primitives
│   ├── mesh/                   # Mesh repair and surface reconstruction
│   ├── pipeline/               # Runner, stages, and typed artifacts
│   ├── pointcloud/             # Outlier filtering and downsampling
│   ├── printability/           # 2-manifold and watertightness checks
│   ├── reconstruction/         # Replaceable photogrammetry engine adapters
│   ├── scaling/                # ArUco fiducial metric calibration
│   ├── utils/                  # Subprocess, hashing, paths, and logging
│   ├── validation/             # Ground-truth dimensional error calculation
│   └── video/                  # Ingest, metadata, and frame extraction
├── tests/                      # Automated test suite
│   ├── fixtures/               # Test fixtures (meshes, images, videos)
│   ├── integration/            # Multi-module and pipeline integration tests
│   └── unit/                   # Deterministic unit tests
├── pyproject.toml              # Build system and package specification
└── README.md                   # This document
```

---

## Quickstart

### 1. Environment Verification
```powershell
.venv\Scripts\python scripts/environment_check.py
```

### 2. Run Test Suite
```powershell
.venv\Scripts\python -m pytest tests/ -v
```

### 3. CLI Execution (Dry-Run Mode)
```powershell
.venv\Scripts\python -m loom --config configs/default.yaml --dry-run
```

### 4. Phase 1 Pipeline Run (Video Ingest & Keyframe Selection)
```powershell
# Run against a smartphone video:
.venv\Scripts\python -m loom --video path/to/video.mp4

# Run with development settings:
.venv\Scripts\python -m loom --config configs/development.yaml --video path/to/video.mp4
```

### 5. Phase 2 Reconstruction Run (3D Mesh Generation)
```powershell
# Run Phase 1 + Phase 2 (Meshroom 3D reconstruction):
.venv\Scripts\python -m loom --video path/to/video.mp4 --reconstruct

# Run with explicit Meshroom binary path:
.venv\Scripts\python -m loom --video path/to/video.mp4 --reconstruct --meshroom-path "C:\Tools\Meshroom-2023.3.0\meshroom_batch.exe"

# Diagnostic check for Meshroom availability:
.venv\Scripts\python scripts/reconstruction_smoke_test.py
```

### 6. Phase 3 Geometry Processing & Mesh Cleanup
```powershell
# Run Phase 3 standalone geometry processing on a raw mesh:
.venv\Scripts\python -m loom geometry --input path/to/raw_mesh.obj

# Or run directly via flag:
.venv\Scripts\python -m loom --mesh path/to/raw_mesh.ply
```


