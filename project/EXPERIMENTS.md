# EXPERIMENT LOG & MEASUREMENTS — VIDEO2PRINT

**Notice on Empirical Integrity**: All numerical results, dimensions, timings, and error metrics recorded in this document must originate from actual physical experiments or verifiable program runs. **Zero fabrication is tolerated.** Empty fields indicate unrun experiments.

---

## Experiment Entry Schema

When documenting an experiment, use this exact structure:

```markdown
### EXP-XXX: [Descriptive Title]
- **Date**: YYYY-MM-DD
- **Target Object**: [Description, material, surface characteristics]
- **Ground-Truth Measurements**:
  - Measurement Tool: [e.g. Digital Calipers (±0.02 mm)]
  - Dimensions (L x W x H mm): [e.g. 50.00 x 50.00 x 50.00 mm]
  - Additional Ground Truth: [Known volume, critical feature diameters]
- **Capture Conditions**:
  - Camera Device: [e.g. iPhone 13 Pro rear main camera]
  - Resolution & FPS: [e.g. 1920x1080 @ 30 fps]
  - Lighting: [e.g. Diffuse indoor softbox, ~450 lux]
  - Trajectory: [e.g. 360-degree single-level orbit at ~0.5m distance]
  - Reference Fiducial: [e.g. ArUco Dict 4x4_50, printed 50.00 mm side length]
- **Pipeline Configuration**:
  - Total Raw Frames: [N]
  - Selected Keyframes: [K]
  - Frame Selection Criteria: [Laplacian threshold, overlap %]
  - Reconstruction Backend: [e.g. Meshroom 2023.3 CLI / AliceVision]
  - Mesh Processing Settings: [Poisson depth, smoothing iterations]
- **Reconstructed Measurements**:
  - Reconstructed Dimensions (L x W x H mm): [Measured in mesh coordinate space]
  - Scale Factor Applied ($s$): [Scale multiplier]
- **Quantitative Error Metrics**:
  - Absolute Error (mm): [|Measured - GroundTruth|]
  - Relative Error (%): [|Measured - GroundTruth| / GroundTruth * 100]
  - Hausdorff Distance: [Mean / Max if CAD reference available]
- **Mesh Statistics**:
  - Vertex Count: [V]
  - Face Count: [F]
  - Watertight? [Yes / No]
  - Non-Manifold Edges: [Count]
- **Execution Timings**:
  - Frame Extraction: [Time in seconds]
  - Quality Selection: [Time in seconds]
  - 3D Reconstruction: [Time in seconds]
  - Mesh Processing: [Time in seconds]
  - Total Pipeline Duration: [Time in seconds / minutes]
- **Failure Observations & Artifacts**:
  - [Note any holes, surface roughness, tracking loss, non-manifold geometry, or missing details]
- **Conclusion & Next Steps**:
  - [Actionable takeaway from the experiment]
```

---

## Logged Experiments

| Exp ID | Date | Object | Frames (Raw/Sel) | Backend | Mean Error (mm) | Rel Error (%) | Watertight? | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| EXP-001 | 2026-09-26 | Synthetic Test Pattern (640x480) | 60 / 5 | Phase 1 Only | N/A (Pre-reconstruction) | N/A | N/A | **VERIFIED** |

---

### EXP-001: Synthetic Video Ingest & Optical Quality Pipeline Verification
- **Date**: 2026-09-26
- **Target Object**: Synthetic generated video (`data/raw/synthetic_test.mp4`) with controlled variations:
  - Frames 0..19: Sharp geometric pattern with moving shapes
  - Frames 20..29: Gaussian blur (ksize=31)
  - Frames 30..39: Underexposed (mean brightness ~20)
  - Frames 40..49: Overexposed (mean brightness ~245)
  - Frames 50..59: Static identical pattern (redundant)
- **Capture Conditions**:
  - Source: Deterministic OpenCV VideoWriter (`mp4v`)
  - Resolution & FPS: 640x480 @ 30.0 fps (2.00s duration, 60 frames)
- **Pipeline Configuration**:
  - Config: `configs/default.yaml` (`sample_interval=1`, `sharpness_threshold=100.0`, `redundancy_threshold=0.98`)
  - Extraction: Streaming sequential JPEG (quality=95)
- **Measured Empirical Results**:
  - Total Raw Frames Extracted: 60
  - Accepted Keyframes: 5 (copied to `frames/selected/`)
  - Rejected Frames: 55
    - Discarded as blurry: 30
    - Discarded for exposure/contrast defects: 20
    - Discarded as near-duplicate/redundant: 26
  - Measured Average Sharpness: 411.36
  - Viewpoint Diversity Score: 0.083
- **Execution Timings & Resource Metrics**:
  - Frame Extraction: ~0.10s
  - Quality Evaluation & Filtering: ~0.93s
  - Total Phase 1 Pipeline: ~1.05s
  - Peak Memory: < 80 MB (zero accumulating frame buffer in RAM)
- **Artifacts Produced**:
  - `outputs/runs/run_20260926_185927_synthetic_test/frames/raw/` (60 JPEGs + `manifest.json`)
  - `outputs/runs/run_20260926_185927_synthetic_test/frames/selected/` (5 JPEGs)
  - `outputs/runs/run_20260926_185927_synthetic_test/reports/metadata.json`
  - `outputs/runs/run_20260926_185927_synthetic_test/reports/capture_analysis.json`
  - `outputs/runs/run_20260926_185927_synthetic_test/logs/pipeline.log`
- **Conclusion & Next Steps**:
  - Verified streaming sequential frame extraction and deterministic gating without memory leaks or whole-video buffering.
  - Ready for Phase 2 reconstruction backend integration.
