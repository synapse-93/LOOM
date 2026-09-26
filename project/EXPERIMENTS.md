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

*(No experiments executed yet. The repository is in Phase 0 Bootstrap state. Real experiments will be logged here sequentially starting in Phase 1 / Phase 2).*

| Exp ID | Date | Object | Frames (Raw/Sel) | Backend | Mean Error (mm) | Rel Error (%) | Watertight? | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| *Template* | *YYYY-MM-DD* | *Object name* | *N / K* | *Backend* | *--* | *--* | *--* | *PENDING* |
