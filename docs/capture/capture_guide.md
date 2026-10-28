# Smartphone Capture Protocol for Photogrammetry

This document defines the standard manual capture procedure for providing real smartphone video inputs to LOOM / VIDEO2PRINT.

---

## 1. Physical Target Selection

Photogrammetry relies on multi-view feature point matching across adjacent camera angles.

- **Recommended Objects**:
  - Textured ceramics (matte coffee mug with printed artwork or texture)
  - Footwear (sneakers, hiking boots with fabric/leather texture)
  - Textured plastic/wood items (wooden figurine, 3D printed benchy with visible layer lines, matte tool casing)
  - Small cardboard boxes with detailed printing
- **Objects to Avoid (Not Supported in Raw SfM)**:
  - Transparent glass or liquids
  - Highly reflective, polished chrome or gloss plastics
  - Featureless monotone surfaces (plain untextured white cube)
  - Moving, flexible, or deformable objects

---

## 2. Environment & Lighting Setup

1. **Stationary Object**: The object must remain 100% stationary throughout the entire capture. Never rotate the object on a turntable unless the background is completely non-textured and lighting rotates with the object.
2. **Diffuse Illumination**: Use soft, even, multi-directional lighting (e.g. indirect daylight from a window or diffused LED ring).
3. **Avoid Dynamic Shadows & Glare**: Hard direct sunlight creates moving highlights as the phone camera orbits, which causes feature matching failures.
4. **Matte Background**: Place the target on a matte, textured surface (wooden desk, cutting mat, or paper with printed markings).

---

## 3. Camera Movement Protocol

1. **Resolution & Framerate**: Set smartphone camera to **1080p (1920x1080) or 4K (3840x2160) at 30 FPS**.
2. **Camera Settings**:
   - Lock Exposure and Focus (AE/AF lock) on the target object before recording to prevent sudden brightness shifts.
   - Turn off digital zoom.
3. **Capture Trajectory**:
   - **Ring 1 (Low Elevation, ~30°)**: Complete one full 360° orbit around the object at a steady, slow pace (approx. 20–30 seconds).
   - **Ring 2 (High Elevation, ~60°)**: Complete a second full 360° orbit looking down at the top features (approx. 20–30 seconds).
   - Maintain 60%–80% visual overlap between adjacent viewpoints.
   - Smooth, continuous motion: Minimize rapid panning or jerking to prevent motion blur.
4. **Duration**: 40 to 60 seconds total.

---

## 4. Ingesting Video into LOOM

1. Transfer the recorded `.mp4` or `.mov` file to your workstation.
2. Place the video file in `data/raw/`:
   ```bash
   cp my_capture.mp4 data/raw/ceramic_mug.mp4
   ```
3. Run LOOM Phase 1 (Ingest & Frame Selection):
   ```bash
   python -m loom --video data/raw/ceramic_mug.mp4
   ```
4. Inspect the summary in the terminal and check `outputs/runs/<run_id>/reports/capture_analysis.json`.
5. Run Phase 2 (3D Reconstruction) once Meshroom is installed:
   ```bash
   python -m loom --video data/raw/ceramic_mug.mp4 --reconstruct
   ```
   Or if Meshroom is installed in a non-standard location:
   ```bash
   python -m loom --video data/raw/ceramic_mug.mp4 --reconstruct --meshroom-path "C:\Tools\Meshroom-2023.3.0\meshroom_batch.exe"
   ```

---

## 5. Interpreting Capture-Quality Metrics

LOOM evaluates individual frames using the following checks:

| Metric | What it measures | Important limitation |
|---|---|---|
| Sharpness | Laplacian variance, used as an indicator of image sharpness | Affected by image content, noise, and resolution |
| Brightness | Mean grayscale intensity | Does not independently establish good lighting |
| Contrast | Standard deviation of grayscale intensity | Low contrast does not necessarily mean low texture |
| Redundancy | Similarity between normalized frame thumbnails | Similarity does not prove that two viewpoints are geometrically identical |
| Low-texture heuristic | Currently reuses the Laplacian-variance score with a separate threshold | Not an independent texture measurement or proof of reconstruction failure |
| Diversity score | Fraction of candidate frames accepted by the current quality filter | Not a measurement of 3D surface coverage or viewpoint diversity |

### Interpreting warnings

- **Blur or low sharpness:** Capture more steadily and avoid rapid camera movement.
- **Underexposure or overexposure:** Adjust lighting and exposure settings.
- **Low contrast:** Improve diffuse illumination and avoid scenes with little grayscale variation.
- **Low visible detail:** Prefer objects with stable, visible surface features. This warning uses a provisional threshold and may overlap with blur detection.
- **High redundancy or low accepted-frame ratio:** Review the sequence for repeated views, rejected frames, and missing viewpoints.

These checks provide capture-quality guidance only. An accepted frame sequence does not guarantee successful 3D reconstruction, accurate dimensions, a complete mesh, or a printable model.

The default low-texture threshold is provisional. It must be evaluated against representative real captures before being treated as a validated cutoff.

## 6. Repeatable Physical-Capture and Measurement Protocol

### 6.1 Record the test conditions

For each capture session, record:

- Capture ID and date
- Object name and material
- Object dimensions measured with a caliper, in millimetres
- Caliper resolution or stated measurement uncertainty, if known
- Smartphone model and camera used
- Video resolution, frame rate, and camera settings
- Lighting and background conditions
- Capture duration and planned viewpoints
- Whether a known-size ArUco reference marker was used and its configured physical size

Keep the object stationary. Capture multiple viewpoints with stable lighting and sufficient visual overlap.

### 6.2 Reference-marker setup

If marker-based scale evaluation is planned, use an ArUco marker with a known physical size and record that size and its units.

Record whether the marker was detected and whether its physical size was actually incorporated into a valid 3D measurement process. Detecting a marker in a 2D image alone does not establish the object's 3D dimensions.

If the marker-to-3D measurement integration is unavailable, record the measurement experiment as blocked or not implemented.

### 6.3 Run and record the evaluation

For each capture:

1. Run LOOM using the documented ingestion command.
2. Record the run ID and input video path.
3. Record candidate, selected, and rejected frame counts.
4. Record blur, exposure, redundancy, and low-texture warning counts when available.
5. Record the reconstruction status and runtime if reconstruction is attempted.
6. Inspect the output mesh and record visible holes, missing surfaces, and other defects.
7. Record export status and any errors.
8. Compare reconstructed dimensions with caliper measurements only when valid reconstructed dimensions are available.

Do not invent missing values. Use `Not run`, `Unavailable`, `Blocked`, or `Not implemented` as appropriate.

## 7. Capture Benchmark Log

Create one entry per actual capture run. Keep separate entries for different objects or capture conditions.

| Field | Observation |
|---|---|
| Capture ID | |
| Date | |
| Object and material | |
| Caliper dimensions (mm) | |
| Reference marker size (mm), if used | |
| Smartphone and camera settings | |
| Resolution and frame rate | |
| Lighting and background | |
| Capture duration | |
| Candidate / selected / rejected frames | |
| Quality warnings | |
| Reconstruction status | |
| Reconstruction runtime | |
| Dimensional error (mm), if measurable | |
| Mesh findings | |
| Export status | |
| Failures and notes | |

Only enter observations from experiments that were actually performed. An empty field does not indicate success.

### Physical-print validation

If a suitable 3D printer is available, record printer and material settings, slicing status, print completion, and measured dimensions of the printed object.

If printing is unavailable, explicitly record physical-print validation as `Not performed — printer unavailable`. Do not claim printability based only on successful mesh export.
