# Phase 4 — Metric Scaling Specification

## 1. Executive Summary & Status Boundary

Phase 4 implements the fiducial metric scaling subsystem of LOOM / VIDEO2PRINT. In monocular multi-view 3D reconstruction (SfM / MVS), scale cannot be recovered from visual parallax alone; the resulting 3D mesh is defined up to an unknown arbitrary scalar factor $\lambda$. Phase 4 solves this scale ambiguity by measuring a known physical reference marker (such as an ArUco fiducial) present in the scene, estimating the true physical scale factor, and applying a deterministic transformation to rescale the cleaned Phase 3 intermediate mesh to real-world millimeters.

> [!IMPORTANT]
> **Definitive Status Boundary**:
> - **Software Implementation**: CODE COMPLETE
> - **Synthetic Geometry Validation**: VERIFIED (31 unit & integration tests, 155 total tests passing)
> - **Physical Accuracy Validation**: PENDING LIVE PHYSICAL EXPERIMENT (Requires physical object capture with physical ArUco fiducial and live photogrammetry backend execution on host `ISSUE-BLK-002`)
> - **Dependencies**: Zero new third-party dependencies added; uses existing `opencv-python==5.0.0.93` (`cv2.aruco`), `numpy`, and `trimesh`.

---

## 2. Mathematical Formulation & Architecture

### 2.1 Core Scaling Relationship
The metric scale factor $s$ relating real-world millimeters to reconstructed coordinate units is defined as:

$$s = \frac{d_{\text{physical}}}{d_{\text{reconstructed}}}$$

Where:
- $d_{\text{physical}}$ is the ground-truth physical dimension of the reference marker in millimeters (e.g., $50.00\text{ mm}$).
- $d_{\text{reconstructed}}$ is the corresponding measured dimension of the reference marker in the reconstructed coordinate space.

### 2.2 Deterministic Vertex Transformation
To avoid arbitrary coordinate displacement, mesh vertex coordinates $\mathbf{p} \in \mathbb{R}^3$ are transformed about an explicit transformation center $\mathbf{p}_{\text{origin}}$ (default: $(0.0, 0.0, 0.0)$):

$$\mathbf{p}_{\text{scaled}} = \mathbf{p}_{\text{origin}} + s \cdot (\mathbf{p} - \mathbf{p}_{\text{origin}})$$

When $\mathbf{p}_{\text{origin}} = (0, 0, 0)$, this simplifies to linear coordinate scaling $\mathbf{p}_{\text{scaled}} = s \cdot \mathbf{p}$, preserving relative vectors and mesh topology without unwanted origin centering or translation.

### 2.3 Decoupled Architectural Flow

```
┌────────────────────────────────────────────────────────┐
│ Capture Video / Keyframes with Visible Reference Marker│
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Phase 2 Photogrammetry / 3D Reconstruction             │
│ (Produces raw mesh + camera trajectory in SfM space)   │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Phase 3 Raw Geometry Cleanup                           │
│ (Removes noise, repairs defects, preserves coordinates)│
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Phase 4 Metric Scaling Subsystem                                       │
│                                                                        │
│   A. Reference Detection (`aruco.py`):                                 │
│      Detects 2D marker ID and corners in captured frames.              │
│                                                                        │
│   B. Reference Measurement (`measurement.py`):                         │
│      Aggregates measured perimeter edge distances across observations; │
│      computes mean, median, standard deviation, and spread.            │
│                                                                        │
│   C. Scale Estimation (`measurement.py`):                              │
│      Estimates scale factor $s = d_{\text{phys}} / d_{\text{recon}}$;  │
│      derives statistical confidence from variance.                     │
│                                                                        │
│   D. Mesh Transformation (`transform.py`):                             │
│      Applies $s$ to vertex coordinates about $\mathbf{p}_{\text{orig}}$;│
│      preserves face indices, vertex count, and topology.               │
│                                                                        │
│   E. Report Generation (`processor.py`):                               │
│      Writes machine-readable `reports/scaling.json`.                   │
└───────────────────────────┬────────────────────────────────────────────┘
                            │
                            ▼
METRICALLY SCALED MESH (`outputs/runs/<run_id>/scaling/scaled_<stem>.obj`)
                            │
                            ▼
PHASE 5 (Geometry & Ground-Truth Dimensional Validation)
```

---

## 3. Module Responsibilities

| Module | Primary Class | Responsibility |
| :--- | :--- | :--- |
| `src/loom/scaling/models.py` | `ReferenceMarker`, `ReferenceMeasurement`, `ScaleEstimate`, `ScalingResult` | Explicit typed data contracts and JSON serialization. |
| `src/loom/scaling/aruco.py` | `ArucoDetector` | OpenCV ArUco dictionary resolution, 2D corner detection, and target ID filtering. |
| `src/loom/scaling/measurement.py` | `MeasurementEngine`, `ScaleEstimator` | Multi-observation distance aggregation, 3D perimeter calculation, and scale estimation. |
| `src/loom/scaling/transform.py` | `ScaleTransformer` | Topology-preserving coordinate rescaling about explicit origin. |
| `src/loom/scaling/processor.py` | `ScalingProcessor` | End-to-end pipeline orchestrator, validation, and report generation. |
| `src/loom/scaling/calibration.py` | `ScaleCalibrator` | Backward-compatible calibration interface. |

---

## 4. Configuration Schema

Configuration is managed via `ScalingConfig` in `src/loom/config/models.py` and supports both flat and structured YAML formats:

```yaml
scaling:
  enabled: false

  reference:
    type: "aruco"
    dictionary: "DICT_4X4_50"
    marker_id: 0
    size_mm: 50.0

  measurement:
    min_observations: 2
    tolerance: 0.05

  transformation_origin: [0.0, 0.0, 0.0]
```

---

## 5. CLI Usage

Phase 4 exposes a dedicated subcommand in the LOOM CLI:

```bash
# Basic scaling invocation
python -m loom scale \
    --input outputs/runs/<run_id>/geometry/cleaned_model.obj \
    --reference-size 50.0 \
    --measured-size 25.0

# With explicit output directory and custom config
python -m loom scale \
    --input outputs/cleaned.obj \
    --output-dir outputs/scaled \
    --config configs/default.yaml \
    --reference-size 50.0 \
    --measured-size 25.0 \
    --marker-id 0
```

---

## 6. Strict Non-Goals & Architectural Boundaries

Phase 4 is strictly bounded to intentional metric scaling and coordinate transformation:
- **No Mesh Cleanup or Repair**: Mesh cleanup belongs exclusively to **Phase 3**. Phase 4 must not alter face topology or fill holes.
- **No Implicit Centering or Normalization**: Phase 4 scales about an explicit origin and does not translate the mesh to origin or unit bounding box.
- **No AI Depth or Neural Prior Models**: Scale recovery is purely deterministic and grounded in physical fiducial geometry.
- **No Manufacturing Slicing / Printability**: Wall thickness and overhangs belong to **Phase 6**.
- **No Claim of Live Physical Accuracy**: Real-world dimensional validation belongs to **Phase 5**.
