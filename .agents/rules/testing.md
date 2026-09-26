# TESTING PHILOSOPHY & VERIFICATION RULES — VIDEO2PRINT

**Scope**: Test methodology, fixture management, and verification requirements for VIDEO2PRINT.

---

## 1. Testing Philosophy

1. **Independent Testability**:
   - Every single pipeline module (video decoding, frame selection, mesh processing, metric scaling, validation, printability, export) must be independently testable.
   - Downstream geometry modules must not require running a full 20-minute photogrammetry pipeline to test hole-filling or watertightness.
2. **Deterministic & Fast Unit Tests**:
   - Unit tests must be fast (< 5 seconds total) and completely deterministic.
   - Test mathematical transforms, coordinate scaling, ArUco corner calculations, normal computations, and manifold checks with known ground-truth inputs.
3. **Integration Tests with Controlled Test Fixtures**:
   - Provide minimal, version-controlled synthetic fixtures (e.g. synthetic geometric meshes like cubes, cylinders, and spheres with known millimeter dimensions, small synthetic video clips, or mock frames).
   - Use these fixtures to verify end-to-end integration across stages.
4. **No Faked or Hallucinated Test Results**:
   - Never write assertion passes that check trivial constants or mock away the very logic under test.
   - When testing external reconstruction engines, unit tests may mock the subprocess call to verify argument parsing and output handling, but integration tests must distinctly run against actual binaries and real input files.

---

## 2. Test Architecture & Structure

Tests are organized cleanly under `tests/`:

```
tests/
├── unit/
│   ├── test_video_ingest.py        # Decoding, metadata parsing, timestamp checks
│   ├── test_frame_selection.py     # Sharpness metrics, laplacian variance, filtering
│   ├── test_mesh_processing.py     # Clean-up, non-manifold repair, Poisson surface
│   ├── test_metric_scaling.py      # Scale factor calculation from fiducials
│   ├── test_validation.py          # Hausdorff distance, bounding box calculation
│   ├── test_printability.py        # Watertightness, normal orientation, overhangs
│   └── test_export.py              # STL serialization, manifest generation
├── integration/
│   ├── test_pipeline_integration.py # Multi-stage pipeline with synthetic fixtures
│   └── test_reconstruction_adapter.py # Real/mock adapter execution tests
└── fixtures/
    ├── meshes/                     # Known geometric models (e.g. 20mm cube, sphere)
    └── synthetic_frames/           # Lightweight test frames with known ArUco markers
```

---

## 3. Verification Standards Before Completion

Before any agent marks an iteration complete or updates `CONTEXT.md`:
1. All unit tests must pass cleanly.
2. No broken imports or unhandled warnings in test suites.
3. Tests must be runnable using standard command:
   ```powershell
   .venv\Scripts\python -m pytest tests/unit/
   ```
4. Verification evidence (actual test logs and outputs) must be reported in the agent response.
