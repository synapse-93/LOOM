# PYTHON STANDARDS & ENVIRONMENT RULES — VIDEO2PRINT

**Scope**: Language standards, dependency management, code conventions, and environment setup for VIDEO2PRINT.

---

## 1. Python Runtime & Environment

1. **Python Version**: Target runtime is **Python 3.10.11**.
   - On Windows host systems with multiple Python versions installed, invoke via:
     ```powershell
     py -3.10 -m venv .venv
     ```
   - Always activate and use the dedicated project virtual environment (`.venv`).
2. **Virtual Environment Isolation**:
   - Never install packages into global Python interpreters.
   - The virtual environment must live in `.venv/` at the repository root and must be ignored by git.
3. **Reproducibility**:
   - Dependencies must be pinned in `requirements.txt`.
   - Maintain reproducible package sets; verify package versions across installations.

---

## 2. Dependency Management Rules

1. **Lean Dependency Set**:
   The baseline project dependencies are restricted to:
   - `numpy`: Numerical operations, vector math, transformation matrices.
   - `opencv-python`: Video decoding, frame processing, ArUco marker detection.
   - `open3d`: Point cloud and 3D mesh processing, normal estimation.
   - `trimesh`: Watertightness, mesh topology, manifold checks, volume and surface area.
   - `pymeshlab`: Advanced mesh filters, remeshing, hole filling, Poisson reconstruction.
   - `scipy`: Spatial indexing, KD-trees, optimization, distance transforms.
   - `tqdm`: Deterministic CLI progress reporting for long-running batch operations.
   - `pyyaml`: Configuration file parsing.
2. **Prohibited Dependencies (Unless Formally Justified)**:
   - No PyTorch, torchvision, or TensorFlow.
   - No heavy deep-learning dependencies (Depth Anything, SAM, NeRF/Gaussian Splatting frameworks).
   - No CUDA runtime toolkits in the primary Python environment (external photogrammetry tools may leverage their own CUDA binaries independently).
3. **Justification Policy**:
   - Every newly added package must be justified in `project/CONTEXT.md` and `project/DECISIONS.md`.

---

## 3. Code Conventions & Standards

1. **Path Handling**:
   - **Always** use `pathlib.Path` for filesystem manipulations.
   - **Never** perform string concatenation (`+ "\path"`) or manual string slicing for paths.
   - Use `.resolve()` for absolute path normalization.
2. **Type Annotations**:
   - Provide type annotations on all function signatures, dataclasses, and class attributes:
     ```python
     from pathlib import Path
     from typing import Sequence

     def extract_frames(video_path: Path, output_dir: Path, sample_interval: int = 1) -> list[Path]:
         ...
     ```
3. **Structured Logging**:
   - Use Python's built-in `logging` module.
   - Never use raw `print()` for pipeline diagnostics or execution flow.
   - Configure a standardized logger per module:
     ```python
     import logging
     logger = logging.getLogger(__name__)
     ```
4. **Configuration Over Hardcoding**:
   - Never hardcode input paths, thresholds, quality levels, or target dimensions.
   - Use dataclasses or YAML configuration files loaded through a centralized config loader.
5. **Defensive Error Handling**:
   - Raise explicit, descriptive domain exceptions rather than generic `Exception` or silent failures.
   - Create a hierarchy under `Video2PrintError`:
     ```python
     class Video2PrintError(Exception):
         """Base exception for VIDEO2PRINT."""

     class VideoIngestError(Video2PrintError):
         """Raised when a video cannot be opened, decoded, or validated."""

     class ReconstructionError(Video2PrintError):
         """Raised when photogrammetry backend fails or produces invalid output."""

     class ScalingError(Video2PrintError):
         """Raised when metric scale cannot be recovered."""

     class PrintabilityError(Video2PrintError):
         """Raised when a mesh fails printability validation."""
     ```
6. **Deterministic Execution**:
   - Where pseudo-random algorithms are employed (e.g. RANSAC, point sampling), set and propagate an explicit integer `random_state` or `seed`.

---

## 4. Pragmatic Tooling Policy

- Do not prematurely introduce complex linters, formatting bots, or build systems that burden development velocity.
- Follow PEP 8 style naturally.
- Use simple, direct execution commands:
  ```powershell
  .venv\Scripts\python -m pytest tests/
  ```
