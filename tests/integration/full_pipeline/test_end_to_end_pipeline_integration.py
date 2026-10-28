"""Comprehensive end-to-end pipeline integration test connecting all stages.

Tests feasible handoffs across:
  1. YAML configuration -> Frame quality assessment
  2. Configuration -> COLMAP command construction & argument routing
  3. Photogrammetry / defective mesh -> Phase 3 geometry cleanup & repair
  4. Cleaned mesh -> Phase 4 metric scaling
  5. Scaled mesh -> Phase 6 printability report generation
  6. Validated mesh -> Phase 7 STL model export
"""

from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pytest
import trimesh

from loom.config.loader import load_config
from loom.capture.quality import FrameQualityAssessor
from loom.reconstruction.colmap import ColmapAdapter
from loom.reconstruction.models import ReconstructionJobConfig
from loom.mesh.processor import MeshProcessor
from loom.scaling.processor import ScalingProcessor
from loom.printability.report import PrintabilityReportGenerator
from loom.export.stl import StlExporter
from tests.fixtures.mesh_fixtures import (
    create_hole_mesh,
    create_photogrammetry_raw_mesh,
    save_fixture_mesh,
)


def test_full_pipeline_cross_stage_handoff(tmp_path: Path) -> None:
    """Verify data contracts across all pipeline stages from YAML to STL export."""
    # -------------------------------------------------------------------------
    # Stage 1: YAML Configuration
    # -------------------------------------------------------------------------
    yaml_file = tmp_path / "pipeline_test.yaml"
    yaml_file.write_text(
        """
name: "integration_test_pipeline"
capture:
  sharpness_threshold: 90.0
  min_texture_score: 18.0
  min_brightness: 25.0
mesh:
  clean_outliers: true
  close_holes: true
  fill_holes: true
  max_hole_size: 25
  max_hole_edges: 30
  component_strategy: "largest"
  unify_normals: true
scaling:
  enabled: true
  strategy: "aruco"
  marker_id: 0
  marker_size_mm: 50.0
printability:
  check_manifold: true
  check_watertight: true
  min_wall_thickness_mm: 1.0
  max_overhang_angle_deg: 45.0
export:
  format: "stl"
  binary: true
""",
        encoding="utf-8",
    )

    config = load_config(yaml_file)
    assert config.name == "integration_test_pipeline"
    assert config.capture.min_texture_score == 18.0
    assert config.mesh.fill_holes is True
    assert config.scaling.marker_size_mm == 50.0

    # -------------------------------------------------------------------------
    # Stage 2: Capture Quality Assessment using loaded configuration
    # -------------------------------------------------------------------------
    assessor = FrameQualityAssessor(config.capture)
    test_frame = tmp_path / "frame_sample.png"
    # Create test pattern with high texture (checkerboard)
    pattern = np.zeros((100, 100), dtype=np.uint8)
    pattern[::10, :] = 255
    pattern[:, ::10] = 255
    import cv2
    cv2.imwrite(str(test_frame), pattern)

    quality_result, _ = assessor.evaluate_frame(test_frame)
    assert quality_result.sharpness > config.capture.sharpness_threshold
    assert quality_result.is_accepted is True
    assert quality_result.is_low_texture is False

    # -------------------------------------------------------------------------
    # Stage 3: COLMAP Command Construction & Argument Routing
    # -------------------------------------------------------------------------
    colmap_args = [
        "--FeatureExtraction.max_num_features", "4096",
        "--FeatureMatching.max_ratio", "0.75",
        "--Mapper.min_num_matches", "20",
    ]
    fe_args = ColmapAdapter._extract_subcommand_args("feature_extractor", colmap_args)
    fm_args = ColmapAdapter._extract_subcommand_args("exhaustive_matcher", colmap_args)
    mapper_args = ColmapAdapter._extract_subcommand_args("mapper", colmap_args)

    assert fe_args == ["--FeatureExtraction.max_num_features", "4096"]
    assert fm_args == ["--FeatureMatching.max_ratio", "0.75"]
    assert mapper_args == ["--Mapper.min_num_matches", "20"]

    # -------------------------------------------------------------------------
    # Stage 4: Mesh Processing on Hole-Defective Mesh -> Repaired to Watertight
    # -------------------------------------------------------------------------
    raw_mesh = create_hole_mesh()
    raw_mesh_file = tmp_path / "hole_mesh_raw.obj"
    save_fixture_mesh(raw_mesh, raw_mesh_file)

    cleaned_mesh_file = tmp_path / "cleaned_mesh.obj"
    mesh_processor = MeshProcessor(config.mesh)
    processing_result = mesh_processor.process(raw_mesh_file, cleaned_mesh_file)

    assert processing_result.success is True
    assert cleaned_mesh_file.is_file()
    assert processing_result.diagnostics_after is not None
    assert processing_result.diagnostics_after.is_watertight is True

    # -------------------------------------------------------------------------
    # Stage 5: Phase 4 Metric Scaling
    # -------------------------------------------------------------------------
    scaled_mesh_file = tmp_path / "scaled_mesh.obj"
    scaling_processor = ScalingProcessor(config.scaling)
    # Known marker size = 50.0 mm, reconstructed reference size = 25.0 units -> scale factor = 2.0
    scaling_result = scaling_processor.process(
        input_mesh_path=cleaned_mesh_file,
        output_mesh_path=scaled_mesh_file,
        reference_measurements=25.0,
    )

    assert scaling_result.success is True
    assert scaling_result.scale_factor == pytest.approx(2.0)
    assert scaled_mesh_file.is_file()

    # -------------------------------------------------------------------------
    # Stage 6: Printability Analysis on Scaled Watertight Mesh
    # -------------------------------------------------------------------------
    print_report = PrintabilityReportGenerator.generate_report(
        scaled_mesh_file, config=config.printability
    )

    assert print_report.is_watertight is True
    assert print_report.is_manifold is True
    assert print_report.min_wall_thickness_mm is not None
    assert print_report.is_printable is True

    report_json_path = tmp_path / "printability.json"
    PrintabilityReportGenerator.export_json(print_report, report_json_path)
    assert report_json_path.is_file()

    # -------------------------------------------------------------------------
    # Stage 7: STL Model Export
    # -------------------------------------------------------------------------
    stl_output_path = tmp_path / "manufacturable_model.stl"
    exporter = StlExporter()
    exported_stl = exporter.export(scaled_mesh_file, stl_output_path, binary=config.export.binary)

    assert exported_stl.is_file()
    assert exported_stl.stat().st_size > 0

    # Reload exported STL and verify geometry integrity
    stl_mesh = trimesh.load(exported_stl, force="mesh", process=False)
    scaled_mesh = trimesh.load(scaled_mesh_file, force="mesh", process=False)
    np.testing.assert_allclose(stl_mesh.bounds, scaled_mesh.bounds, rtol=1e-5, atol=1e-6)


def test_full_pipeline_raw_photogrammetry_open_mesh(tmp_path: Path) -> None:
    """Verify that open photogrammetry surfaces pass through cleaning, scaling, and export gracefully."""
    raw_mesh = create_photogrammetry_raw_mesh(radius=10.0)
    raw_mesh_file = tmp_path / "photogrammetry_raw.obj"
    save_fixture_mesh(raw_mesh, raw_mesh_file)

    cleaned_mesh_file = tmp_path / "cleaned_photogrammetry.obj"
    mesh_processor = MeshProcessor()
    processing_result = mesh_processor.process(raw_mesh_file, cleaned_mesh_file)

    # Photogrammetry mesh cleaning succeeds, removing dust clusters and small defects
    assert processing_result.success is True
    assert cleaned_mesh_file.is_file()
    assert processing_result.diagnostics_after is not None
    # Open unobserved base is preserved per photogrammetry expectations
    assert processing_result.diagnostics_after.boundary_loop_count >= 1

    # Scaling operates successfully on the open photogrammetry mesh
    scaled_mesh_file = tmp_path / "scaled_photogrammetry.obj"
    scaling_processor = ScalingProcessor()
    scaling_result = scaling_processor.process(
        input_mesh_path=cleaned_mesh_file,
        output_mesh_path=scaled_mesh_file,
        reference_measurements=20.0,
    )
    assert scaling_result.success is True
    assert scaled_mesh_file.is_file()

    # Printability analyzer gracefully reports open surface without crashing
    print_report = PrintabilityReportGenerator.generate_report(scaled_mesh_file)
    assert print_report.is_watertight is False
    assert print_report.min_wall_thickness_mm is None
    assert print_report.is_printable is False
    assert any("open" in w.lower() or "watertight" in w.lower() for w in print_report.warnings)

    # STL exporter successfully exports the unscaled or scaled mesh
    stl_file = tmp_path / "photogrammetry.stl"
    exported_stl = StlExporter().export(scaled_mesh_file, stl_file, binary=True)
    assert exported_stl.is_file()
    assert exported_stl.stat().st_size > 0
