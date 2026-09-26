# RESEARCH INTEGRITY & EMPIRICAL RIGOR — VIDEO2PRINT

**Scope**: Research integrity, measurement protocol, benchmark validity, and scientific documentation for VIDEO2PRINT.

---

## 1. Zero Tolerance for Data Fabrication

1. **No Fabricated Measurements**:
   - Every metric, dimension, execution duration, triangle count, Hausdorff distance, and dimensional error value recorded in [`project/EXPERIMENTS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/EXPERIMENTS.md) or project documentation must be directly measured from an actual program run or calibrated instrument.
   - Fabricating numbers to demonstrate "high precision" or "99.8% accuracy" is strictly prohibited.
2. **No Hallucinated Citations**:
   - Do not invent paper titles, authors, DOIs, or benchmark numbers.
   - Any external references cited must be real, verifiable peer-reviewed or standard engineering sources.
3. **No Unsupported Novelty Claims**:
   - Do not claim that an algorithm or approach is "novel", "state-of-the-art", or "first of its kind" without empirical comparison against established baselines (e.g. standard AliceVision baseline, raw COLMAP, baseline naive frame extraction).

---

## 2. Implementation Facts vs. Research Findings

Agents and contributors must strictly distinguish between:
- **Implementation Facts**: What the software is programmed to do (e.g., "The module detects ArUco marker 4x4_50 and calculates the Euclidean distance between corners in 2D space").
- **Research Findings**: What empirical experiments have demonstrated under controlled conditions (e.g., "On a 50.0 mm calibration cube under diffuse 400 lux indoor lighting, the pipeline achieved an absolute mean dimensional error of 1.4 mm (2.8% relative error)").

---

## 3. Experimental Protocol & Reproducibility

Every experiment recorded in [`project/EXPERIMENTS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/EXPERIMENTS.md) must document:
1. **Physical Ground Truth**:
   - Ground truth dimensions must be measured using calibrated physical tools (e.g., digital vernier calipers with $\pm 0.02\text{ mm}$ rated resolution) or known CAD dimensions of standard calibration targets.
2. **Capture Conditions**:
   - Device model (e.g., iPhone 13, Samsung Galaxy S22).
   - Video resolution and frame rate (e.g., 1080p @ 30fps).
   - Trajectory style (e.g., $360^\circ$ single-orbit, multi-height orbital capture, distance ~0.5m).
   - Environmental illumination (e.g., indoor fluorescent, direct sunlight, diffuse softbox).
   - Object surface properties (matte, specular, translucent, featureless).
3. **Transparent Reporting of Failures**:
   - Engineering and scientific progress relies on understanding failure boundaries.
   - Always report tracking loss, feature match failures, non-manifold geometry, surface holes, scale recovery errors, and negative results alongside successes.
