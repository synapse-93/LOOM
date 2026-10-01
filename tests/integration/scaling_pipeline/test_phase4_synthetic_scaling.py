"""Integration tests for Phase 4 synthetic metric scaling and CLI execution."""

from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pytest
import trimesh

from loom.__main__ import main
from loom.pipeline.runner import run_phase4_scaling_pipeline
from loom.scaling.processor import ScalingProcessor
from tests.fixtures.mesh_fixtures import create_clean_cube


def test_synthetic_scaling_exact_dimensions(tmp_path: Path) -> None:
    """Verify synthetic mesh of known extent 25.0 is metrically scaled to exact 50.0 mm."""
    # Create a box of extents [25.0, 25.0, 25.0]
    box = trimesh.creation.box(extents=(25.0, 25.0, 25.0))
    in_mesh = tmp_path / "synthetic_box_25.obj"
    box.export(str(in_mesh))

    out_mesh = tmp_path / "scaled_box_50.obj"

    # Known physical reference: 50.0 mm
    # Measured reconstructed reference: 25.0 units
    # Scale factor: 50.0 / 25.0 = 2.0
    processor = ScalingProcessor()
    result = processor.process(
        input_mesh_path=in_mesh,
        output_mesh_path=out_mesh,
        reference_measurements=25.0,
    )

    assert result.status == "SUCCESS"
    assert result.scale_factor == pytest.approx(2.0)

    # Check scaled mesh dimensions
    reloaded = trimesh.load(str(out_mesh), process=False)
    np.testing.assert_allclose(reloaded.extents, [50.0, 50.0, 50.0], rtol=1e-5)
    assert len(reloaded.vertices) == len(box.vertices)
    assert len(reloaded.faces) == len(box.faces)
    np.testing.assert_array_equal(reloaded.faces, box.faces)


def test_synthetic_scaling_translated_and_rotated(tmp_path: Path) -> None:
    """Verify metric scaling preserves relative coordinates on translated and rotated mesh."""
    # Box created, then translated and rotated
    box = trimesh.creation.box(extents=(10.0, 20.0, 30.0))
    translation = np.array([100.0, -200.0, 300.0])
    box.apply_translation(translation)

    in_mesh = tmp_path / "translated_box.obj"
    box.export(str(in_mesh))

    out_mesh = tmp_path / "scaled_translated_box.obj"

    # Known = 50.0, Reconstructed = 100.0 -> Scale factor = 0.5
    processor = ScalingProcessor()
    result = processor.process(
        input_mesh_path=in_mesh,
        output_mesh_path=out_mesh,
        reference_measurements=100.0,
    )

    assert result.status == "SUCCESS"
    assert result.scale_factor == pytest.approx(0.5)

    reloaded = trimesh.load(str(out_mesh), process=False)
    # Extents [10, 20, 30] * 0.5 = [5, 10, 15]
    np.testing.assert_allclose(reloaded.extents, [5.0, 10.0, 15.0], rtol=1e-5)
    # Centroid: translation * 0.5 = [50, -100, 150]
    np.testing.assert_allclose(reloaded.centroid, translation * 0.5, rtol=1e-4)


def test_scaling_ratio_variations(tmp_path: Path) -> None:
    """Verify various scaling ratios: 1.0 (identity), 0.5 (downscale), 2.0 (upscale)."""
    cube = create_clean_cube()  # 2x2x2 cube
    in_mesh = tmp_path / "cube.obj"
    cube.export(str(in_mesh))

    processor = ScalingProcessor()

    # Identity: known 50, measured 50 -> scale 1.0
    r_id = processor.process(in_mesh, tmp_path / "scale_1.obj", reference_measurements=50.0)
    assert r_id.scale_factor == pytest.approx(1.0)
    m_id = trimesh.load(str(tmp_path / "scale_1.obj"), process=False)
    np.testing.assert_allclose(m_id.extents, [2.0, 2.0, 2.0])

    # Downscale: known 50, measured 100 -> scale 0.5
    r_half = processor.process(in_mesh, tmp_path / "scale_half.obj", reference_measurements=100.0)
    assert r_half.scale_factor == pytest.approx(0.5)
    m_half = trimesh.load(str(tmp_path / "scale_half.obj"), process=False)
    np.testing.assert_allclose(m_half.extents, [1.0, 1.0, 1.0])

    # Upscale: known 50, measured 10 -> scale 5.0
    r_5 = processor.process(in_mesh, tmp_path / "scale_5.obj", reference_measurements=10.0)
    assert r_5.scale_factor == pytest.approx(5.0)
    m_5 = trimesh.load(str(tmp_path / "scale_5.obj"), process=False)
    np.testing.assert_allclose(m_5.extents, [10.0, 10.0, 10.0])


def test_run_phase4_scaling_pipeline(tmp_path: Path) -> None:
    """Verify run_phase4_scaling_pipeline generates scaled mesh and valid scaling.json report."""
    cube = create_clean_cube()
    in_mesh = tmp_path / "cube_input.obj"
    cube.export(str(in_mesh))

    out_dir = tmp_path / "pipeline_run"
    result, report_path = run_phase4_scaling_pipeline(
        mesh_path=in_mesh,
        reference_measurements=25.0,
        output_dir=out_dir,
    )

    assert result.status == "SUCCESS"
    assert report_path.is_file()

    with open(report_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["status"] == "SUCCESS"
    assert data["scale_factor"] == 2.0
    assert data["vertex_count_before"] == 8
    assert data["vertex_count_after"] == 8
    assert Path(data["output_mesh_path"]).is_file()


def test_phase4_cli_execution(tmp_path: Path) -> None:
    """Verify dedicated Phase 4 CLI: `python -m loom scale --input ... --reference-size 50.0 --measured-size 25.0`."""
    cube = create_clean_cube()
    in_mesh = tmp_path / "cli_cube.obj"
    cube.export(str(in_mesh))
    out_dir = tmp_path / "cli_out"

    exit_code = main([
        "scale",
        "--input", str(in_mesh),
        "--output-dir", str(out_dir),
        "--reference-size", "50.0",
        "--measured-size", "25.0",
    ])

    assert exit_code == 0
    report_file = out_dir / "reports" / "scaling.json"
    assert report_file.is_file()

    with open(report_file, "r", encoding="utf-8") as f:
        report = json.load(f)

    assert report["status"] == "SUCCESS"
    assert report["scale_factor"] == 2.0
