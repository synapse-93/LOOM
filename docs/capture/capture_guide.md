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
