# ITERATION CHANGELOG — VIDEO2PRINT

This log records chronological development iterations. Every agent completing meaningful work must add an entry following this format.

---

## Iteration 015 — Multi-Model SfM Selection, Delaunay Spike Elimination & Dense Sampling Evaluation
- **Date**: 2026-10-29
- **Milestone**: Remediation of single-model SfM selection defect in multi-component COLMAP reconstructions, elimination of Delaunay meshing edge spikes via side-length regularization, empirical evaluation of dense frame sampling (120 candidate frames), and photogrammetric adequacy validation (223 total tests passed).
- **Defects Identified, Reproduced & Resolved**:
  - **Single-Model SfM Selection Defect in Multi-Component COLMAP Reconstructions**:
    - *Defect*: When incremental mapping produces multiple disjoint sparse reconstructions (`sparse/0`, `sparse/1`, `sparse/2`, ...), `ColmapAdapter.reconstruct` unconditionally defaulted to `sparse/0`. On the 120-frame test video run, `sparse/0` was a discarded preliminary 5-camera fragment (209 points), while `sparse/1` contained the primary reconstruction with 21–24 registered cameras, 874–983 points, and 3.80 mean track length.
    - *Remediation*: Implemented `_get_model_stats()` in `src/loom/reconstruction/colmap.py` to inspect binary (`images.bin`, `points3D.bin`) or text (`images.txt`, `points3D.txt`) model metadata. Replaced unconditional `sparse/0` binding with dynamic selection maximizing `(registered_images, points_count, file_count)`.
    - *Regression Tests*: Added `test_select_best_model_prefers_larger_model` in `tests/unit/reconstruction/test_colmap_adapter.py`.
  - **Delaunay Meshing Outlier Spikes on Sparse Point Clouds**:
    - *Defect*: On sparse SfM models with isolated background points, COLMAP's default `--DelaunayMeshing.max_side_length_factor 25` allowed massive edges up to 24.7m connecting foreground and outlier points, creating large spiky triangles stretching the bounding box extent to 28.8m.
    - *Remediation*: Configured `--DelaunayMeshing.max_side_length_factor 10` by default in `ColmapAdapter.reconstruct()`, suppressing wild outlier edges and constraining mesh extents to the tight scene volume (8.63m x 11.14m x 3.68m) while preserving fine object geometry.
  - **Reconstruction Adequacy & Failure Discrimination (Step 3)**:
    - *Defect*: Prior implementation treated any non-empty PLY file as unconditional `ReconstructionStatus.SUCCESS`, even when registration ratio was 20% or point counts were too sparse to faithfully represent surface topology.
    - *Remediation*: Added validation in `ColmapAdapter.reconstruct()`: enforces `registered_cameras >= 3` (raising `ReconstructionExecutionError` otherwise), discriminates fragmented reconstructions (< 35% registration coverage on >= 10 frames) by assigning `ReconstructionStatus.PARTIAL`, and packages informative diagnostics in `error_message`.
    - *Regression Tests*: Added `test_fragmented_reconstruction_marked_partial` and `test_insufficient_registered_cameras_raises_error` in `test_colmap_adapter.py`.
- **Verification**:
    - Full test suite: **223 passed in 10.76s** (100% pass rate).
    - Empirical validation on mouse video (`video_20261029_152036.mp4`):
      - Registered cameras increased from **6** (baseline) to **21** (+250%).
      - Reconstructed 3D points increased from **184** (baseline) to **874** (+375%).
      - Surface mesh faces increased from **120** (baseline) to **914** (+661%).
      - Median edge length decreased from **0.690** to **0.210** (-69.6% tighter).

---

## Iteration 014 — Reconstruction-Aware Frame Selection & Optical Connectivity
- **Date**: 2026-10-29
- **Milestone**: Implementation of opt-in reconstruction-aware frame selection (`selection_mode = "reconstruction_aware"`), multi-factor optical analysis, pairwise geometric verification ($F$ vs $H$ with RANSAC) across sliding temporal window ($K=3$), bridge frame prioritization, redundancy suppression, and Windows test fixture stabilization (220 total tests passed).
- **Defects Identified, Reproduced & Resolved**:
  - **Single Hard Cutoff & Match-Graph Disconnection Under Quality Filter**:
    - *Defect*: When processing smartphone video `video_20261029_152036.mp4` (63.22s, 3,778 frames), the default quality filter evaluated frames with a hard sharpness cutoff (`sharpness < 80.0`), rejecting 43 of 60 frames and clustering 14 frames in $t=16$s–$32$s with a 24-second tracking void before 3 frames at $t=56$s–$59$s. The resulting COLMAP match graph contained 4 disconnected components and homography-dominated pairs ($H/F > 0.95$), causing bundle adjustment to fail with `Discarding reconstruction due to bad initial pair`.
    - *Remediation*: Implemented `ReconstructionAwareSelector` in `src/loom/capture/reconstruction_aware.py`. It partitions candidate frames into uniform temporal sectors ensuring full duration coverage, evaluates multi-factor optical utility (sharpness, contrast, exposure, keypoint density, grid distribution), computes Fundamental matrix $F$ vs Homography $H$ RANSAC inliers across a local sliding window ($K=3$), discriminates planar/rotational degeneracy ($H/F \ge 0.85$), prioritizes bridge frames linking disconnected graph components, and suppresses visually redundant frames. Configurable via `CaptureConfig` fields (`selection_mode`, `target_selected_frames`, `min_inlier_matches`, `max_homography_inlier_ratio`, `temporal_window_size`, `enable_geometric_verification`). 100% backward compatibility preserved for `selection_mode = "default"`.
    - *Regression Tests*: Added 10 comprehensive tests in `tests/unit/capture/test_reconstruction_aware.py` covering full timeline coverage, avoidance of clustering, homography degeneracy detection, bridge frame prioritization, visual redundancy suppression, graceful fallback for disabled/missing geometric data, defective frame rejection with explicit reasons, deterministic selection, default mode backward compatibility, and configuration validation.
  - **Python Garbage Collection Crash on Windows from OpenCV C++ Subclassing**:
    - *Defect*: `test_frame_extraction_handles_unknown_frame_count` subclassed `cv2.VideoCapture` in Python. Because `cv2.VideoCapture` is a C extension type without a Python-friendly subclassable layout, Python's GC crashed during teardown with an unraisable exception access violation in `gc_collect_harder`.
    - *Remediation*: Refactored test fixture to use composition (`VideoCaptureWrapper`) delegating to `self._real` rather than subclassing the OpenCV C type, completely resolving the Windows GC access violation.
- **Verification**:
    - Unit & integration test suite: **220 passed in 8.25s** (100% pass rate).
    - Preserved existing functionality: default mode filtering behaves identically to prior iterations.

---

## Iteration 013 — Full-Duration Capped Frame Sampling & Circular Import Remediation
- **Date**: 2026-10-29
- **Milestone**: Remediation of frame extraction premature truncation under max_frames cap, elimination of circular import between loom.video and loom.pipeline, and full duration coverage verification (210 total tests passed).
- **Defects Identified, Reproduced & Resolved**:
  - **Full-Duration Frame Sampling Under max_frames Limit**:
    - *Defect*: When max_frames capped frame extraction (e.g. 60 frames on a 63.22s, 3,778-frame 60fps video with target_fps 15 / step 4), FrameExtractor stopped immediately upon writing frame 236 (t = 3.95s), ignoring the remaining 59.27s (93.75%) of the video. Sharp orbital viewpoints later in the video were never evaluated.
    - *Remediation*: In src/loom/video/frames.py, when source_frame_count > 0 and max_frames > 0 and total nominal samples exceed max_frames, the sampling interval step dynamically expands to max(step, source_frame_count // max_frames). This guarantees exactly max_frames samples distributed uniformly across the entire video duration up to the final seconds.
    - *Regression Tests*: Added test_frame_extraction_spans_entire_video_when_capped, test_frame_extraction_preserves_target_fps_when_under_max_frames, test_frame_extraction_adjusts_step_when_target_fps_exceeds_max_frames, and test_frame_extraction_handles_unknown_frame_count in tests/unit/video/test_frames.py.
  - **Module-Level Circular Import in Video Package**:
    - *Defect*: Importing loom.video.frames or loom.video.ingest directly triggered from loom.pipeline.artifacts import FrameSetArtifact / VideoArtifact, which executed loom/pipeline/__init__.py -> runner.py -> stages.py -> from loom.video.frames import FrameExtractor, failing with an ImportError on partially initialized module.
    - *Remediation*: Shifted FrameSetArtifact and VideoArtifact imports behind TYPE_CHECKING at module level and imported locally inside extract() and ingest() methods, completely decoupling loom.video initialization from loom.pipeline.
- **Verification**:
    - Unit & integration test suite: **210 passed in 7.93s** (100% pass rate).
    - Empirical validation on real smartphone video (video_20261029_152036.mp4): extracted exactly 60 frames spanning from t = 0.0s to t = 61.21s (96.82% duration coverage, effective step = 62), compared to prior 3.95s (6.25% coverage).

---

## Iteration 012 — Comprehensive Cross-Stage Integration Debugging, Defect Remediation & Full-Pipeline Verification
- **Date**: 2026-10-28
- **Milestone**: Full cross-stage pipeline debugging, test-first remediation of 6 integration defects, unified printability report orchestrator, and comprehensive end-to-end integration tests (206 total passed).
- **Defects Identified, Reproduced & Resolved**:
  - **Capture Configuration Loading & Attribute Safety**:
    - *Defect*: `min_texture_score` was dropped by `_parse_dict_to_config` in `src/loom/config/loader.py`, causing custom texture thresholds in YAML to be lost. Additionally, line 125 of `src/loom/capture/quality.py` accessed `self.config.min_texture_score` directly, causing `AttributeError` on configurations lacking the field.
    - *Remediation*: Added `min_texture_score` parsing in `loader.py` and safe attribute extraction with fallback in `quality.py`.
    - *Regression Tests*: `test_load_capture_config_custom_fields` in `test_config.py` and `test_frame_quality_assessor_handles_config_without_min_texture_score` in `test_quality.py`.
  - **Mesh Configuration Field Persistence**:
    - *Defect*: `loader.py` dropped 10 of 15 `MeshConfig` fields (`fill_holes`, `max_hole_edges`, `component_strategy`, `min_component_faces`, `min_component_ratio`, `remove_degenerate_faces`, `remove_unreferenced_vertices`, `remove_duplicate_faces`, `unify_normals`, `degenerate_area_threshold`), discarding user-supplied mesh settings and causing boolean `False` values or `0.0` values to be dropped.
    - *Remediation*: Explicitly unpacked and preserved all 15 `MeshConfig` parameters in `_parse_dict_to_config`, correctly preserving booleans set to `False` and zero numeric values.
    - *Regression Tests*: `test_load_mesh_config_all_fields` and `test_load_mesh_config_defaults_preserved` in `test_config.py`.
  - **CLI Arguments & Numeric Downsampling Options**:
    - *Defect*: Passing lowercase `--log-level debug` exited with status code 2 due to case-sensitive `argparse` choices. Furthermore, setting `pointcloud.voxel_downsample_size: 0.0` was dropped by truthiness check `if p.get("voxel_downsample_size")`.
    - *Remediation*: Added case conversion (`type=lambda v: v.upper()`) in CLI `--log-level` and changed check to `if p.get("voxel_downsample_size") is not None`.
    - *Regression Tests*: `test_cli_log_level_case_insensitive`, `test_cli_log_level_invalid_rejected`, and `test_load_pointcloud_voxel_downsample_zero`.
  - **COLMAP Argument Routing & Workspace Cleanup**:
    - *Defect*: COLMAP rejected unrecognized options when passed globally. Setting `keep_workspace=False` did not clean up the intermediate `images/` directory or database.
    - *Remediation*: Implemented `_extract_subcommand_args` routing namespaced flags (`--FeatureExtraction.*`, `--FeatureMatching.*`, `--Mapper.*`, `--DelaunayMeshing.*`) to matching subcommands. Implemented safe intermediate artifact cleanup preserving mesh, cloud, and log.
    - *Regression Tests*: `test_colmap_additional_args_routing` and `test_colmap_keep_workspace_false` in `test_colmap_adapter.py`.
  - **Printability Report Orchestration for Open Meshes**:
    - *Defect*: Missing unified orchestrator `PrintabilityReportGenerator.generate_report`. Downstream `WallThicknessAnalyzer` raised an unhandled `ValueError` when run on non-watertight meshes.
    - *Remediation*: Implemented `generate_report` running all 4 checkers sequentially, gracefully recording open/non-watertight warnings without throwing exceptions and marking `min_wall_thickness_mm = None`.
    - *Regression Tests*: `test_generate_report_watertight_cube`, `test_generate_report_open_mesh_graceful`, `test_generate_report_nonexistent_mesh_raises`, and `test_generate_report_and_export_roundtrip`.
  - **Full-Pipeline End-to-End Integration Tests**:
    - *Implementation*: Added `tests/integration/full_pipeline/test_end_to_end_pipeline_integration.py` validating data handoffs across: YAML config -> Frame quality -> COLMAP command routing -> Phase 3 cleanup -> Phase 4 scaling -> Phase 6 printability -> Phase 7 STL export.
- **Verification**:
  - Full test suite: **206 passed in 16.23s** (100% pass rate).
  - Safety constraints verified: `colmap/` untouched, zero commits pushed to remote GitHub.

---

## Iteration 011 — Unmerged Phase 4 Branch Audit & Full Codebase Consolidation Verification
- **Date**: 2026-10-28
- **Milestone**: Full repository audit and consolidation of all branches; unmerged origin/feature/phase-4-scaling (PR #1) evaluated and verified superseded by production Phase 4 (PR #2); full test suite verified (191 passed).
- **Changes & Decisions**:
  - Conducted complete audit across all remote and local branches (origin/main, origin/akash/printability-stl-export, origin/contributor-c-capture-quality, origin/phase4-metric-scaling, origin/feature/phase-4-scaling, and PRs #1-#4).
  - Evaluated commit 7e5da69 on origin/feature/phase-4-scaling against the production Phase 4 implementation. Confirmed that 7e5da69 removed 983 lines of architecture to introduce an early 128-line prototype (ScaleConfig, ScaleResult, MetricScalingProcessor, detect_aruco_corners, calculate_reconstructed_distance, apply_mesh_scale), which was subsequently superseded by production PR #2 (origin/phase4-metric-scaling, commit 862211e merged via 399077e).
  - Determined that all capabilities represented in 7e5da69 are already implemented in production in a strictly superior, typed, and mathematically robust form (ScalingProcessor, ArucoDetector, MeasurementEngine, ScaleTransformer, ReferenceMarker, ScaleEstimate, ScalingResult).
  - Left duplicate and simplified classes (ScaleConfig, ScaleResult, MetricScalingProcessor) out of production to avoid API collision and architectural regression, preserving the full 35-test Phase 4 test suite.
  - Verified that colmap/ remains untouched, no git merge -s ours hack was applied, and zero changes were pushed to GitHub.
- **Verification**:
  - Full test suite execution: **191 passed in 16.00s** (100% pass rate).
  - All submodules verified: video ingest, capture quality, COLMAP CPU photogrammetry, Meshroom compatibility, geometry processing and repair, Phase 4 metric scaling, printability analysis, and STL export.
  - CLI commands verified: loom --help, loom geometry --help, loom scale --help.
  - Working tree clean.

---

## Iteration 010 — Integration with Latest GitHub Main: Capture Guidance, Printability Checks & STL Export
- **Date**: 2026-10-28
- **Milestone**: Full integration of local COLMAP/Phase 4 work with latest origin/main features (Capture texture guidance, Phase 6 mesh printability analyzers, Phase 7 STL model export). Total: 191 passing tests.
- **Changes Integrated**:
  - Integrated remote contributions: low-texture quality heuristic, non-guarantee capture guidance, ManifoldChecker, WatertightChecker, WallThicknessAnalyzer (using rtree ray intersections), OverhangAnalyzer, PrintabilityReportGenerator, and StlExporter.
  - Preserved all local work: COLMAP CPU photogrammetry adapter, relative Qt platform plugin resolution, SQLite match verification, CPU matching retry, Delaunay meshing, empty-input pre-flight guard, and CLI backend options.
  - Resolved project/EXPERIMENTS.md experiment ID collision: retained teammate capture-quality test as EXP-008, renumbered local live photogrammetry run to EXP-009, and renumbered empty-input run to EXP-010.
  - Added unit test suite tests/unit/export/test_stl_export.py covering binary and ASCII STL export, error handling, and bounds invariance.
  - Installed rtree==1.4.1 into .venv for raycast wall-thickness verification.
- **Verification**:
  - Full test suite: 191 passed in 13.56s (100% pass rate across all modules).
  - Targeted verification across COLMAP adapter, Meshroom adapter, capture quality, Phase 4 metric scaling, printability checkers, and STL export: 106 passed in 3.30s.
  - Local colmap/ directory preserved and untouched.
  - Zero commits pushed to remote repository.

---

## Iteration 009 — COLMAP Windows CPU Reconstruction Pipeline, Qt Plugin Resolution & Live End-to-End Verification
- **Date**: 2026-10-28
- **Milestone**: Phase 2 — COLMAP Photogrammetry Backend EMPIRICALLY VERIFIED on Windows Host; Phase 1 -> Phase 2 -> Phase 3 Live Handoff Verified (179 passing tests).
- **Changes Implemented**:
  - Extended COLMAP executable resolution to support direct executable paths, directories containing colmap.exe, and installation directories containing bin/colmap.exe without hardcoding machine-specific paths.
  - Implemented automatic Qt platform plugin discovery discovering relative plugins/platforms directory (containing qwindows.dll) and injecting QT_QPA_PLATFORM_PLUGIN_PATH into subprocess environment while preserving existing user environment variables.
  - Added binary capability probing (probe_capabilities) to detect builds compiled 'without GPU support' and enforce explicit CPU flags (--FeatureExtraction.use_gpu 0, --FeatureMatching.use_gpu 0).
  - Implemented silent matcher failure detection and SQLite database match counting (_count_database_matches) on database.db, automatically retrying on CPU if GPU matching silently fails and preventing invalid execution from continuing to mapper.
  - Implemented CPU-compatible reconstruction path: feature_extractor -> exhaustive_matcher -> mapper -> model_converter (sparse points.ply) -> delaunay_mesher (sparse surface mesh.ply).
  - Added PLY mesh validation (_validate_ply_mesh) verifying non-empty vertex and face elements before declaring reconstruction success.
  - Implemented dense MVS capability checking (patch_match_stereo requires CUDA/HIP); preserved sparse point clouds and Delaunay meshes when dense is unavailable or fails, keeping sparse and dense artifact paths distinct in ReconstructionResult.
  - Implemented zero-selected-frames pre-flight check in src/loom/pipeline/runner.py, cleanly skipping external engine invocation, setting ReconstructionStatus.INVALID_INPUT, and providing actionable camera guidance when all frames fail quality filtering.
  - Added comprehensive unit tests in tests/unit/reconstruction/test_colmap_adapter.py and tests/unit/reconstruction/test_cli_backend_options.py, and tests/unit/pipeline/test_empty_input_reconstruction.py.
- **Verification**:
  - Full test suite: **179 passed in 9.86s** (100% pass rate, zero regressions, zero warnings).
  - Live COLMAP run on smartphone footage (WhatsApp Video 2026-10-28 at 20.16.26.mp4): extracted 300 frames, selected 158 keyframes, matched 12,403 pairs on CPU, triangulated sparse cloud (118 points), generated Delaunay mesh (89 vertices, 158 faces) in 241.45s.
  - Live Phase 3 handoff: mesh processor diagnosed 1 boundary loop (18 edges), repaired with 16 triangles, produced watertight solid (89 vertices, 174 faces, watertight=True, Euler=2, volume=0.0031) saved to outputs/live-test/runs/.../geometry/cleaned_mesh.obj.
  - Live empty-input smoke test on blurry video (WIN_20261028_20_24_03_Pro.mp4): rejected all 300 frames for motion blur (sharpness 12.63), skipped reconstruction with status invalid_input in 0.00s and generated clear capture guidance.
- **Next Steps**:
  - Execute live capture of physical object with known-size ArUco reference marker to perform end-to-end Phase 4 metric scaling on real photogrammetric meshes.
  - Proceed with Phase 5 ground-truth geometry validation.

---

## Iteration 008 — COLMAP Backend Implementation & Reconstruction Failure Classification
- **Date**: 2026-10-28
- **Milestone**: Phase 2 — COLMAP CLI adapter implemented; live backend execution remains unverified until an external COLMAP installation is available.
- **Changes Implemented**:
  - Replaced the `ColmapAdapter` stub with a subprocess-based COLMAP workflow: feature extraction, exhaustive matching, sparse mapping, image undistortion, PatchMatch stereo, stereo fusion, and Poisson meshing.
  - Added executable resolution for explicit files/directories and `PATH`; validated input frame existence/extensions; isolated generated workspace artifacts; enforced a total-job timeout budget; logged command output and rejected missing/empty dense-cloud or mesh artifacts.
  - Added CLI options `--reconstruction-backend` and `--reconstruction-binary`; retained `--meshroom-path` as a backward-compatible alias.
  - Improved pipeline failure reporting so timeout, unavailable binary, invalid input, and missing artifacts retain distinct `ReconstructionStatus` values instead of all becoming `process_failed`.
  - Added mocked COLMAP adapter tests for successful stage orchestration, binary/input errors, command failures, and missing output artifacts; added CLI option coverage.
  - Updated reconstruction and blocker documentation to distinguish adapter tests from live photogrammetry evidence.
- **Verification**:
  - `PYTHONPATH=src python -m pytest -q`: **163 passed** in the available execution environment. The project targets Python 3.10; rerun in the project's Python 3.10 environment before release.
  - No live COLMAP executable was invoked. Real reconstruction quality, GPU compatibility, registration rate, metric accuracy, and physical printability remain unverified.
- **Next Steps**:
  - Install/locate a compatible COLMAP CLI build and run `scripts/reconstruction_smoke_test.py` or a real COLMAP smoke workflow.
  - Process a real smartphone capture with a known-size physical reference; inspect sparse/dense artifacts and measure dimensional error.

---

## Iteration 007 — Phase 4: Metric Scaling Subsystem Implementation & Synthetic Validation
- **Date**: 2026-10-01
- **Milestone**: Phase 4 — Metric Scaling (IMPLEMENTED & SYNTHETICALLY VERIFIED with 155 total tests; Physical Validation Pending Live Capture with ArUco Fiducial)
- **Changes Implemented**:
  - Audited OpenCV dependency: confirmed `opencv-python==5.0.0.93` provides full native `cv2.aruco` support (`ArucoDetector`, `DetectorParameters`, predefined dictionaries). Zero new dependencies added.
  - Implemented typed domain exceptions in `src/loom/scaling/exceptions.py`: `ScalingError`, `ScalingConfigError`, `ReferenceDetectionError`, `ReferenceMeasurementError`, `ScaleEstimationError`, `MeshScalingError`, `MeshScalingValidationError`.
  - Implemented typed data models in `src/loom/scaling/models.py`: `ReferenceMarker`, `MarkerObservation`, `ReferenceMeasurement`, `ScaleEstimate`, and `ScalingResult` with complete JSON serialization.
  - Implemented ArUco detector in `src/loom/scaling/aruco.py`: dictionary lookup (`DICT_4X4_50`, etc.), 2D corner extraction, target ID filtering, and synthetic marker generation.
  - Implemented measurement & scale estimation engine in `src/loom/scaling/measurement.py`: `MeasurementEngine` (multi-observation distance aggregation, 3D perimeter calculation, rejection of invalid/non-finite measurements) and `ScaleEstimator` ($s = d_{\text{phys}} / d_{\text{recon}}$ with variance and confidence).
  - Implemented deterministic mesh transformer in `src/loom/scaling/transform.py`: `ScaleTransformer` applying vertex scaling $\mathbf{p}_{\text{scaled}} = \mathbf{p}_{\text{orig}} + s \cdot (\mathbf{p} - \mathbf{p}_{\text{orig}})$ about an explicit origin while keeping vertex count, face count, and topology 100% invariant.
  - Implemented scaling orchestrator in `src/loom/scaling/processor.py`: `ScalingProcessor` handling input mesh validation, reference measurement, scale estimation, transformation, output validation, and JSON report generation.
  - Updated configuration models in `src/loom/config/models.py` and `src/loom/config/loader.py`: `ScalingConfig` supporting flat keys and nested YAML syntax with backwards compatibility.
  - Added standalone pipeline runner in `src/loom/pipeline/runner.py`: `run_phase4_scaling_pipeline()` generating `scaled_<stem>.obj` and `reports/scaling.json`.
  - Added dedicated CLI subcommand in `src/loom/__main__.py`: `loom scale --input <mesh> --reference-size <mm> --measured-size <units>` with structured terminal summary.
  - Authored comprehensive specification in `docs/scaling.md`.
  - Added 31 unit and integration tests across `tests/unit/scaling/` and `tests/integration/scaling_pipeline/`.
- **Verification**:
  - Full test suite passed: **155 passed in 7.32s** (100% pass rate, 31 new tests + 124 existing tests, zero regressions, zero warnings).
  - CLI execution verified: `python -m loom scale --input data/raw/sample_photogrammetry_raw.obj --reference-size 50.0 --measured-size 25.0` completed in 0.0055s, producing exact $2.0\times$ scaled mesh and `reports/scaling.json`.
  - Synthetic box ($25\text{ mm} \to 50\text{ mm}$) verified with $0.000\%$ relative error and zero topology distortion.
- **Next Steps**:
  - Provision external reconstruction tool (`meshroom_batch` or `colmap`) to unblock live photogrammetry (`ISSUE-BLK-002`).
  - Execute live smartphone video capture with physical ArUco fiducial to perform physical ground truth accuracy validation.
  - Proceed to Phase 5 (Geometry & Ground-Truth Dimensional Validation).

---

## Iteration 006 — Phase 2 & Phase 3 Validation, Hardening & Pipeline Handoff Audit
- **Date**: 2026-10-01
- **Milestone**: Phase 2 — Reconstruction Backend Integration (Adapter & Contracts Verified; Host Binary BLOCKED `ISSUE-BLK-002`); Phase 3 — Raw Geometry & Mesh Processing (VERIFIED & AUDITED with 124 total tests)
- **Changes Implemented**:
  - Audited host environment photogrammetry executables: searched system PATH, `C:\`, `C:\Program Files`, `C:\Users\adise`, `AppData`, `tools`. Neither `meshroom_batch.exe` nor `colmap.exe` is present on disk (`ISSUE-BLK-002`). Confirmed NVIDIA GeForce RTX 4060 Laptop GPU with Driver 592.82 and CUDA 13.1 ready for photogrammetry binary installation.
  - Phase 2 live reconstruction status kept explicitly marked `BLOCKED` as mandated by project constitution and completion gates.
  - Hardened `MeshroomAdapter` in `src/loom/reconstruction/meshroom.py`:
    - Updated `parse_camera_sfm` to handle both dictionary and list JSON schemas for `views` and `poses`, calculate pose counts, clamp `registration_ratio` to $[0.0, 1.0]$.
    - Added `.stl` candidate extension to mesh discovery, added fallback to `sfm.json` if `cameras.sfm` is absent.
  - Hardened Phase 3 geometry diagnostics and cleanup:
    - Added configurable `degenerate_area_threshold: float = 1e-7` to `MeshConfig` in `src/loom/config/models.py`.
    - Updated `MeshDiagnostics.inspect()` and `MeshCleaner.clean()` to detect and purge collinear sliver triangles while accounting for float serialization rounding differences between memory and disk representations.
    - Suppressed Trimesh internal `RuntimeWarning: invalid value encountered in divide` on open surfaces by guarding `fix_inversion` with `if mesh.is_watertight:` and `warnings.catch_warnings()`.
  - Hardened pipeline orchestration in `src/loom/pipeline/runner.py`:
    - Added safety try/except wrapper around `MeshProcessor.process` in `run_phase1_pipeline`. When a raw mesh is corrupt or unreadable, sets `mesh_processing_result.status = "FAILED"`, writes `geometry.json`, and cleanly separates reconstruction success from geometry processing failure.
    - Added user warning when `--clean-mesh` is requested with video input without `--reconstruct`.
  - Added photogrammetry raw mesh fixture in `tests/fixtures/mesh_fixtures.py` (`create_photogrammetry_raw_mesh`):
    - Synthesized 1040-triangle sphere dome with 40-edge open base boundary, 3-edge pinhole, 2 floating satellite noise clusters, collinear slivers, duplicate faces, unreferenced vertices, and arbitrary SfM offset coordinates.
    - Saved reference raw mesh fixture to `data/raw/sample_photogrammetry_raw.obj`.
  - Added comprehensive test suites (9 new tests):
    - `tests/unit/mesh/test_photogrammetry_audit.py` (6 unit audit tests verifying diagnostics, component selection, cleanup, conservative hole repair, scale/coordinate preservation, and JSON report generation on realistic photogrammetry mesh).
    - `tests/integration/full_pipeline/test_phase2_phase3_handoff.py` (3 integration tests verifying full Phase 1 $\to$ Phase 2 $\to$ Phase 3 handoff, reconstruction failure skipping Phase 3, and failure discrimination between reconstruction success and corrupt mesh processing failure).
- **Verification**:
  - Full test suite passed: **124 passed in 9.28s** (100% pass rate, 9 new tests + 115 existing tests, zero failures, zero warnings).
  - CLI execution verified: `python -m loom geometry --input data/raw/sample_photogrammetry_raw.obj` executed in 0.0508s, producing `cleaned_sample_photogrammetry_raw.obj` and `reports/geometry.json`.
  - Degraded execution verified: `python -m loom --video data/raw/synthetic_test.mp4 --reconstruct --clean-mesh` completed cleanly with `Status: RECONSTRUCTION BLOCKED (Backend Executable Unavailable on Host)`.
- **Next Step**:
  - Provision external reconstruction tool (`meshroom_batch` or `colmap`) to unblock live photogrammetry (`ISSUE-BLK-002`).
  - Proceed with Phase 4 (Fiducial Metric Scaling & Coordinate Transformation).

---

## Iteration 005 — Phase 3: Raw Geometry & Mesh Processing Implementation & Fixture Validation
- **Date**: 2026-10-01
- **Milestone**: Phase 3 — Raw Geometry & Mesh Processing (IMPLEMENTED & FIXTURE-TESTED with 115 tests; Live Reconstruction: Awaiting Host Binary `ISSUE-BLK-002`)
- **Changes Implemented**:
  - Enforced strict Phase 3 architectural boundaries: zero Phase 4+ functionality added (no metric scaling, no ArUco markers, no absolute dimensions, no CAD ground-truth accuracy benchmarking, no printability analysis, no STL manufacturing export, no neural AI/PyTorch/Depth Anything dependencies). Reconstructed coordinates and physical scale strictly preserved.
  - Installed authorized dependencies: `trimesh==5.1.0` and `scipy==1.15.3` (authorized under `.agents/rules/python.md`). Updated `pyproject.toml`.
  - Implemented typed domain exceptions in `src/loom/mesh/exceptions.py`: `MeshError`, `MeshFormatError`, `MeshInvalidError`, `MeshLoadError`, `MeshProcessingError`.
  - Extended configuration models in `src/loom/config/models.py`: added `component_strategy`, `min_component_faces`, `min_component_ratio`, `remove_degenerate_faces`, `remove_unreferenced_vertices`, `remove_duplicate_faces`, `unify_normals`, `max_hole_edges`, `fill_holes`.
  - Implemented typed data models in `src/loom/mesh/models.py`: `GeometryDiagnostics`, `ComponentInfo`, `ComponentActionResult`, `CleanupActionResult`, `RepairActionResult`, `MeshProcessingResult`, and `MeshProcessingStage` enum.
  - Implemented read-only diagnostics in `src/loom/mesh/diagnostics.py`: vertex/face counts, bounding box, extents, volume, surface area, component count, boundary edges, boundary loops, non-manifold edges/vertices, watertightness, Euler characteristic, NaN/Inf detection, zero-area degenerate triangles, duplicate faces, unreferenced vertices, and status categorization (`VALID`, `WARNING`, `ERROR`).
  - Implemented connected component analysis in `src/loom/mesh/components.py`: `MeshComponentAnalyzer` supporting strategies (`largest`, `largest_by_area`, `min_faces`, `relative_threshold`, `keep_all`) based on face-adjacency graph traversal without external graph packages.
  - Implemented deterministic cleanup in `src/loom/mesh/cleanup.py`: `MeshCleaner` removing NaN/Inf vertices, invalid face indices, zero-area degenerate triangles (cross-product area $\le 10^{-12}$), duplicate faces, and unreferenced vertices.
  - Implemented conservative hole repair in `src/loom/mesh/repair.py`: `MeshRepairer` extracting directed boundary loops, classifying defects by size threshold (`max_hole_edges`), triangulating eligible loops via 2D ear-clipping, honestly preserving complex defects in `defect_details`, and unifiying outward normals via pure NumPy BFS without `networkx`.
  - Implemented pipeline orchestrator in `src/loom/mesh/processor.py`: `MeshProcessor` managing the 8-stage pipeline while strictly preserving coordinate values and physical scale.
  - Implemented standalone runner in `src/loom/pipeline/runner.py`: `run_phase3_mesh_pipeline()` generating `outputs/runs/<run_id>/geometry/cleaned_<stem>.obj` and `reports/geometry.json`.
  - Integrated Phase 3 into CLI (`src/loom/__main__.py`): added `geometry` subcommand (`python -m loom geometry --input <mesh>`) and direct flag (`--mesh`), with structured terminal diagnostic summary.
  - Authored comprehensive Phase 3 specification in `docs/geometry.md`.
  - Constructed deterministic test fixtures in `tests/fixtures/mesh_fixtures.py` (`clean_cube`, `disconnected_mesh`, `degenerate_mesh`, `hole_mesh`, `large_hole_mesh`, `duplicate_and_unreferenced_mesh`).
  - Added 40 new unit and integration tests across `tests/unit/mesh/` and `tests/integration/mesh_pipeline/`.
- **Verification**:
  - Full test suite passed: **115 passed in 7.20s** (100% pass rate, 40 new tests + 75 existing tests, zero regressions).
  - Validated all 4 core fixture types through end-to-end pipeline:
    - `clean_cube`: 8 vertices, 12 faces, 1 component, watertight True, SUCCESS.
    - `disconnected`: 12 -> 8 vertices, 16 -> 12 faces, 2 -> 1 component, watertight True, SUCCESS.
    - `degenerate`: 11 -> 8 vertices, 13 -> 12 faces, zero-area face and unreferenced vertices removed, watertight True, SUCCESS.
    - `hole`: 8 -> 8 vertices, 11 -> 12 faces, boundary loop repaired, watertightness restored, SUCCESS.
  - CLI smoke test verified: `python -m loom geometry --input outputs/experiments/phase3_validation/hole.obj` completed with exit code 0, generated valid intermediate mesh and `reports/geometry.json`.
- **Next Step**:
  - Unblock host photogrammetry backend (`ISSUE-BLK-002`) to run live smartphone video through Phase 1 -> Phase 2 -> Phase 3 end-to-end.
  - Begin Phase 4 (Fiducial Metric Scaling & Coordinate Transformation).

---

## Iteration 004 — Phase 2: Architecture, Contracts, Failure Classification & Pipeline Integration

- **Date**: 2026-09-26
- **Milestone**: Phase 2 — Multi-View 3D Reconstruction Integration (Architecture & Adapter: IMPLEMENTED & VERIFIED with 75 tests; Live execution: BLOCKED pending host binary)
- **Changes Implemented**:
  - Enforced strict Phase 2 architectural boundaries: zero Phase 3+ functionality added (no mesh cleanup, no hole repair, no metric scaling, no ArUco detection, no STL export, no heavyweight AI dependencies).
  - Explicitly decoupled software implementation status from live reconstruction experimental validation status.
  - Defined explicit 7-state failure classification enumeration `ReconstructionStatus` (`SUCCESS`, `PARTIAL`, `BINARY_UNAVAILABLE`, `INVALID_INPUT`, `PROCESS_FAILED`, `TIMEOUT`, `ARTIFACT_MISSING`) in `src/loom/reconstruction/models.py`.
  - Defined 8 conceptual reconstruction stages via `ReconstructionStage` enum (Stage 0: Input Validation, Stage 1: Camera Init, Stage 2: Camera Registration, Stage 3: Sparse Reconstruction, Stage 4: Dense Reconstruction, Stage 5: Raw Meshing, Stage 6: Artifact Discovery, Stage 7: Diagnostics).
  - Expanded `ReconstructionResult` and `ReconstructionArtifact` models with decoupled multi-tier artifacts: `sparse_reconstruction_path`, `dense_point_cloud_path`, `raw_mesh_path`, `workspace_path`, `log_path`, `status`, and backward-compatible alias properties.
  - Extended exception hierarchy in `src/loom/reconstruction/exceptions.py` with `ReconstructionInvalidInputError` (inherits from `ValueError` and `FileNotFoundError` for backward compatibility), `ReconstructionTimeoutError` (inherits from `ReconstructionExecutionError`), and `ReconstructionPartialError`.
  - Hardened `MeshroomAdapter` in `src/loom/reconstruction/meshroom.py`:
    - Implemented `DiscoveredArtifacts` dataclass supporting 3-variable tuple unpacking (`mesh, pc, sfm`), sequence indexing, and dictionary access for 100% backward compatibility.
    - Explicitly distinguished dense point clouds (`densePointCloud.ply`, `pointCloud.ply`) from sparse SfM clouds (`cloud_and_poses.ply`, `sfm.ply`).
    - Handled partial reconstructions (`status=PARTIAL`) where sparse/dense point cloud and camera poses were generated but meshing failed or was not produced.
    - Handled missing artifacts (`status=ARTIFACT_MISSING`) when subprocess returns 0 without writing output files.
    - Attached `reconstruction.log` path to `ReconstructionResult`.
  - Updated `src/loom/pipeline/runner.py` and `reports/reconstruction.json` to write standardized schema containing `status`, `sparse_reconstruction`, `dense_point_cloud_path`, `point_cloud_path`, `workspace_path`, and `log_path`.
  - Enhanced CLI (`src/loom/__main__.py`) terminal summary output to display categorized failure state, sparse SFM cloud, dense point cloud, workspace, and log file paths.
  - Authored comprehensive Phase 2 architectural specification in `docs/reconstruction.md`.
  - Added 10 new tests: unit tests in `tests/unit/reconstruction/test_meshroom_adapter.py` (partial reconstruction, artifact missing, timeout subclass, invalid input error types, discovered artifacts properties, reconstruction stage sequence) and integration tests in `tests/integration/reconstruction/test_reconstruction_contract.py` and `tests/integration/video_pipeline/test_phase1_pipeline.py`.
- **Verification**:
  - Full test suite passed: **75 passed in 5.62s** (100% pass rate, zero regressions across all 75 tests).
  - CLI `--help` and `--dry-run` verified.
  - Synthetic pipeline with `--reconstruct` executed on `data/raw/synthetic_test.mp4`: verified graceful degradation (`BINARY_UNAVAILABLE`), non-crashing execution, valid `reports/reconstruction.json` output, and informative terminal summary.
- **Next Step**:
  - Install Meshroom 2023.3 on development host (or pass `--meshroom-path`) and provide a real smartphone capture to run live 3D reconstruction.

---

## Iteration 003 — Phase 1.5 Verification & Hardening, Phase 2: Meshroom 3D Reconstruction Adapter
- **Date**: 2026-09-26
- **Milestone**: Phase 2 — Multi-View 3D Reconstruction Integration (IMPLEMENTED & VERIFIED with mocked subprocess; Live execution BLOCKED by host binary)
- **Changes Implemented**:
  - Independently verified Phase 1 baseline test suite: exactly 52 tests passed in 3.59s with 0 failures, 0 warnings.
  - Fixed documentation drift across the repository: replaced stale `src/video2print/` references with actual `src/loom/` in `project/ROADMAP.md` and `.agents/rules/architecture.md`.
  - Conducted host environment discovery: searched system PATH, standard Windows program directories, and winget registry. Verified that `meshroom_batch`, `aliceVision_*`, and `colmap` are not installed on the development host (`ISSUE-BLK-002`).
  - Extended configuration models (`src/loom/config/models.py`, `loader.py`, `configs/*.yaml`) to support `binary_path: Optional[Path] = None`, `keep_workspace: bool = True`, and `additional_args: list[str]`.
  - Extended result models (`src/loom/reconstruction/models.py`) with `mesh_path`, `point_cloud_path`, `camera_poses_path`, `input_frames_count`, `registered_cameras_count`, `registration_ratio`, `point_count`, `error_message`, and `backend` alias.
  - Implemented typed reconstruction exceptions in `src/loom/reconstruction/exceptions.py`: `ReconstructionError`, `ReconstructionBinaryNotFoundError`, `ReconstructionExecutionError`, `ReconstructionArtifactNotFoundError`.
  - Implemented production `MeshroomAdapter` in `src/loom/reconstruction/meshroom.py`:
    - `resolve_binary()` and `is_available()` checking configuration overrides, environment variables (`MESHROOM_PATH`, `MESHROOM_BIN`), and system PATH.
    - CLI argument construction (`build_command()`) without shell invocation (`shell=False`).
    - AliceVision `cameras.sfm` JSON parser extracting registered camera count and registration ratio.
    - Multi-tier output artifact discovery (`discover_output_artifacts()`) locating `texturedMesh.obj/ply`, `mesh.obj/ply`, `cloud_and_poses.ply`, and `cameras.sfm`.
    - Isolated workspace layout (`outputs/runs/<run_id>/reconstruction/workspace/{input,output,cache,logs}`).
    - Subprocess execution using safe `proc.communicate(timeout=...)` with streaming log capture into `reconstruction.log`.
  - Implemented `ReconstructionRunner` in `src/loom/reconstruction/runner.py` with factory lookup and descriptive error for unsupported backends.
  - Integrated reconstruction into the pipeline runner (`src/loom/pipeline/runner.py`), directly feeding Phase 1 selected keyframes to the reconstruction adapter and generating `reports/reconstruction.json`.
  - Extended CLI (`src/loom/__main__.py`) with `--reconstruct` and `--meshroom-path` flags and comprehensive Phase 2 summary terminal output.
  - Created smartphone capture guide in `docs/capture/capture_guide.md` specifying physical target requirements, lighting, orbital trajectory (two elevation rings), and overlap requirements.
  - Created standalone diagnostic smoke test script in `scripts/reconstruction_smoke_test.py`.
  - Implemented 13 unit tests with mocked subprocess in `tests/unit/reconstruction/test_meshroom_adapter.py` testing missing binary, invalid inputs, command construction, SFM parsing, artifact discovery, successful runs, non-zero return codes, timeouts, and missing mesh failure reporting.
- **Verification**:
  - Full test suite passed: **65 passed in 4.60s** (13 new reconstruction tests + 52 existing tests, 100% pass rate).
  - CLI dry-run verified: `python -m loom --dry-run` passed.
  - CLI Phase 1 verified: `python -m loom --video data/raw/synthetic_test.mp4` passed.
  - CLI Phase 2 graceful degradation verified: `python -m loom --video data/raw/synthetic_test.mp4 --reconstruct` correctly reported missing binary, generated valid `reconstruction.json`, and displayed structured Phase 2 terminal summary.
- **Next Step**:
  - Install Meshroom 2023.3 on development host (or pass `--meshroom-path`) and provide a real smartphone capture to run live 3D reconstruction.

---

## Iteration 002 — Phase 1: Video Ingest, Frame Extraction & Capture Quality
- **Date**: 2026-09-26
- **Milestone**: Phase 1 — Video Ingest, Frame Extraction & Capture Quality (COMPLETED)
- **Changes Implemented**:
  - Installed and pinned Phase 1 dependencies in Python 3.10.11 `.venv`: `numpy==2.2.6`, `opencv-python==5.0.0.93`, `tqdm==4.70.1`.
  - Implemented OpenCV-based video validation and container metadata extraction in `src/loom/video/metadata.py` with robust duration calculation, stream property validation, FourCC decoding, and deterministic `try...finally: cap.release()`.
  - Implemented `VideoIngestor` in `src/loom/video/ingest.py`, validating container formats and producing verified `VideoArtifact`.
  - Implemented sequential streaming frame extraction in `src/loom/video/frames.py` with configurable sampling interval, target FPS, max_frames, JPEG quality encoding, deterministic filenames (`frame_{idx:06d}.jpg`), and machine-readable `manifest.json`. Zero whole-video RAM retention.
  - Implemented deterministic optical quality analysis in `src/loom/capture/quality.py`:
    - Sharpness via Laplacian variance on grayscale images.
    - Brightness via grayscale mean (with configurable min/max exposure rejection).
    - Contrast via grayscale standard deviation (with configurable min contrast threshold).
    - Redundancy filtering via 64x64 thumbnail mean absolute difference against previous accepted frame (`redundancy_threshold=0.98`).
  - Implemented 2D viewpoint diversity estimation in `src/loom/capture/coverage.py` and actionable capture guidance generation in `src/loom/capture/guidance.py`.
  - Implemented Phase 1 pipeline execution in `src/loom/pipeline/runner.py` with standardized output directory structure (`outputs/runs/<run_id>/frames/{raw,selected}`, `reports/{metadata.json,capture_analysis.json}`, `logs/pipeline.log`).
  - Extended CLI (`src/loom/__main__.py`) supporting `--video`, `--config`, `--output-dir`, and outputting rich terminal execution summaries.
  - Completed synthetic test video generator `scripts/generate_test_video.py` producing controlled variations (normal, blurred, dark, bright, redundant frames).
  - Built comprehensive unit tests (`test_metadata.py`, `test_frames.py`, `test_quality.py`) and end-to-end integration tests (`test_phase1_pipeline.py`).
- **Verification**:
  - `pytest tests/ -v` passed all 52 tests (100% pass rate).
  - Synthetic video generation tested: 60 frames @ 30 FPS, 640x480 generated and verified.
  - CLI execution verified: `python -m loom --video data/raw/synthetic_test.mp4` successfully ran end-to-end, extracted 60 frames, filtered defects, copied 5 high-quality keyframes to `frames/selected/`, and generated both JSON reports and log file.
  - Memory & resource safety verified: streaming extraction consumes constant minimal memory (< 80 MB) without accumulative memory growth.
- **Next Step**:
  - Phase 2 Planning: Multi-View 3D Reconstruction Integration (Meshroom / AliceVision CLI adapter).

---

## Iteration 001 — Complete Application Scaffold & Test Hierarchy
- **Date**: 2026-09-26
- **Milestone**: Phase 0 — Application Scaffold & Architecture
- **Changes Implemented**:
  - Installed Python 3.10.11 64-bit on host via winget and activated virtual environment `.venv/` resolving `ISSUE-BLK-001`.
  - Created standard src-layout package `src/loom/` with `pyproject.toml` supporting `python -m loom` CLI.
  - Implemented typed configuration system (`src/loom/config/`) with YAML parser and preset profiles (`configs/default.yaml`, `configs/development.yaml`, `configs/experiment.yaml`).
  - Implemented immutable artifact model (`src/loom/pipeline/artifacts.py`) and pipeline stage contracts (`src/loom/pipeline/stages.py`, `src/loom/pipeline/runner.py`) supporting dry-run verification.
  - Implemented 3D geometric math models (`src/loom/geometry/`) including `Point3D`, `Vector3D`, `BoundingBox3D`, and `TransformMatrix4x4`.
  - Scaffolded interfaces and data contracts across all pipeline stages:
    - `src/loom/video/`: VideoIngestor, VideoMetadata, FrameExtractor (streaming contract)
    - `src/loom/capture/`: FrameQualityAssessor, CoverageEstimator, CaptureGuidance
    - `src/loom/reconstruction/`: ReconstructionEngine ABC, MeshroomAdapter, ColmapAdapter, ReconstructionRunner
    - `src/loom/pointcloud/`: PointCloudCleaner, PointCloudFilter, PointCloudAnalyzer
    - `src/loom/mesh/`: MeshCleaner, MeshRepairer, MeshTopologyAnalyzer, SurfaceReconstructor
    - `src/loom/scaling/`: ArucoDetector, ScaleCalibrator, ScaleTransformer
    - `src/loom/validation/`: DimensionAnalyzer, GeometryComparator, GroundTruthComparison, ValidationReportGenerator
    - `src/loom/printability/`: ManifoldChecker, WatertightChecker, WallThicknessAnalyzer, OverhangAnalyzer, PrintabilityReportGenerator
    - `src/loom/export/`: StlExporter, ExportManifest, ExportReportGenerator
    - `src/loom/utils/`: logging, paths, subprocess, hashing
  - Created test suite hierarchy under `tests/` with 35 unit and integration tests across package imports, configs, artifacts, runner dry-run, geometry math, and stage contracts.
  - Created utility and diagnostic scripts under `scripts/`: `environment_check.py`, `generate_test_video.py`, `generate_marker.py`, `benchmark.py`.
  - Created directory scaffolding for `data/`, `outputs/`, and `docs/` with `.gitkeep` placeholders.
  - Authored architecture overview documentation in `docs/architecture/overview.md`.
  - Updated `README.md` to clearly distinguish Implemented, Scaffolded, and Planned subsystems.
  - Updated `project/CONTEXT.md` and `project/ISSUES.md` (resolved `ISSUE-BLK-001`).
- **Verification**:
  - `python -m loom --help`, `python -m loom --dry-run`, and `python -m loom -c configs/default.yaml --dry-run` execute cleanly.
  - `pytest tests/ -v` passes 35 out of 35 tests with 0 failures and 0 warnings.
  - `scripts/environment_check.py` successfully diagnoses runtime and dependency status.
  - Verified no circular imports, no fake photogrammetry/meshing logic, and proper `NotImplementedError` boundaries on scaffolded interfaces.
- **Next Step**:
  - Phase 1 Kickoff: Implement real streaming video ingest, frame extraction, and Laplacian sharpness quality filtering using OpenCV.

---

## Iteration 000 — Project Bootstrap & Agent Operating System
- **Date**: 2026-09-26
- **Milestone**: Phase 0 — Project Bootstrap
- **Changes Implemented**:
  - Inspected repository state (clean git working tree on branch `main`, Python 3.10.11 registered in `py` launcher but binary missing on disk; active host Python is 3.14.7).
  - Created project constitution [`AGENTS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/AGENTS.md) with core directives, mandatory iteration workflow, and context update protocols.
  - Created architectural rules in [`.agents/rules/architecture.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/architecture.md) detailing pipeline stages, interfaces, and backend replaceability.
  - Created Python standards in [`.agents/rules/python.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/python.md) specifying Python 3.10.11 runtime, lean dependency policy, and logging/path conventions.
  - Created 3D reconstruction rules in [`.agents/rules/reconstruction.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/reconstruction.md) detailing subprocess adapter pattern, monocular scale ambiguity, and ArUco marker scaling.
  - Created testing philosophy in [`.agents/rules/testing.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/testing.md) establishing independent testability and synthetic test fixtures.
  - Created research integrity rules in [`.agents/rules/research.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/.agents/rules/research.md) enforcing zero fabrication of measurements or results.
  - Created current state snapshot in [`project/CONTEXT.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/CONTEXT.md).
  - Created 11-phase staged development plan in [`project/ROADMAP.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/ROADMAP.md).
  - Documented four initial Architecture Decision Records in [`project/DECISIONS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/DECISIONS.md) (ADR-001 through ADR-004).
  - Established schema and empirical logging rules in [`project/EXPERIMENTS.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/EXPERIMENTS.md).
  - Recorded initial discoveries, limitations, and research questions in [`project/ISSUES.md`](file:///c:/Users/adise/OneDrive/Documents/Loom/project/ISSUES.md).
- **Verification**:
  - Validated all 12 project governance and rule files created.
  - Verified no implementation code was falsely marked complete.
  - Verified internal consistency across rules, roadmap, ADRs, and issues.
- **Next Step**:
  - Begin Phase 1: Initialize `.venv` with Python 3.10.11, pin core dependencies in `requirements.txt`, and implement video ingest / frame extraction module with unit tests.
