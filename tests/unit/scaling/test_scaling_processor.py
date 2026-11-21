"""Unit tests for ScalingProcessor pipeline orchestration and error handling."""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest
import trimesh

from loom.config.models import ScalingConfig
from loom.scaling.exceptions import (
    ReferenceMeasurementError,
    ScalingConfigError,
)
from loom.scaling.models import ReferenceMarker
from loom.scaling.processor import ScalingProcessor
from tests.fixtures.mesh_fixtures import create_clean_cube
from tests.unit.scaling.test_aruco import _setup_synthetic_colmap_scene


def test_scaling_processor_successful_execution(tmp_path: Path) -> None:
    """Verify end-to-end ScalingProcessor execution with valid mesh and reference measurement."""
    cube = create_clean_cube()
    in_mesh = tmp_path / "cube.obj"
    cube.export(str(in_mesh))
    out_mesh = tmp_path / "scaled_cube.obj"

    config = ScalingConfig(
        strategy="aruco",
        marker_id=0,
        marker_size_mm=50.0,
        dictionary="DICT_4X4_50",
    )
    processor = ScalingProcessor(config=config)

    # Reconstructed marker size = 25.0 -> expected scale = 50.0 / 25.0 = 2.0
    result = processor.process(
        input_mesh_path=in_mesh,
        output_mesh_path=out_mesh,
        reference_measurements=25.0,
    )

    assert result.status == "SUCCESS"
    assert result.success is True
    assert result.scale_factor == pytest.approx(2.0)
    assert result.vertex_count_before == 8
    assert result.vertex_count_after == 8
    assert result.face_count_before == 12
    assert result.face_count_after == 12
    assert out_mesh.is_file()

    # Verify scaled mesh dimensions doubled: cube originally 2x2x2 -> now 4x4x4
    reloaded = trimesh.load(str(out_mesh), process=False)
    assert reloaded.extents == pytest.approx([4.0, 4.0, 4.0])


def test_scaling_processor_with_multiple_observations(tmp_path: Path) -> None:
    """Verify ScalingProcessor with multi-edge reference measurements."""
    cube = create_clean_cube()
    in_mesh = tmp_path / "cube.obj"
    cube.export(str(in_mesh))
    out_mesh = tmp_path / "scaled_cube.obj"

    processor = ScalingProcessor()
    # 4 edge observations: mean 25.0 -> scale = 50.0 / 25.0 = 2.0
    result = processor.process(
        input_mesh_path=in_mesh,
        output_mesh_path=out_mesh,
        reference_measurements=[25.0, 25.1, 24.9, 25.0],
    )

    assert result.status == "SUCCESS"
    assert result.scale_factor == pytest.approx(2.0)
    assert result.measurement is not None
    assert result.measurement["measurement_count"] == 4


def test_scaling_processor_missing_mesh_file() -> None:
    """Verify processor raises FileNotFoundError or returns FAILED on non-existent input mesh."""
    processor = ScalingProcessor()

    with pytest.raises(FileNotFoundError):
        processor.process(
            input_mesh_path=Path("non_existent_file.obj"),
            reference_measurements=25.0,
            raise_on_error=True,
        )

    res = processor.process(
        input_mesh_path=Path("non_existent_file.obj"),
        reference_measurements=25.0,
        raise_on_error=False,
    )
    assert res.status == "FAILED"
    assert res.success is False
    assert len(res.errors) > 0


def test_scaling_processor_missing_reference_measurement(tmp_path: Path) -> None:
    """Verify processor raises ReferenceMeasurementError or returns INVALID_REFERENCE when no measurement is passed."""
    cube = create_clean_cube()
    in_mesh = tmp_path / "cube.obj"
    cube.export(str(in_mesh))

    processor = ScalingProcessor()

    with pytest.raises(ReferenceMeasurementError):
        processor.process(
            input_mesh_path=in_mesh,
            reference_measurements=None,
            raise_on_error=True,
        )

    res = processor.process(
        input_mesh_path=in_mesh,
        reference_measurements=None,
        raise_on_error=False,
    )
    assert res.status == "INVALID_REFERENCE"
    assert res.success is False


def test_scaling_processor_invalid_marker_size(tmp_path: Path) -> None:
    """Verify processor rejects non-positive marker physical size."""
    cube = create_clean_cube()
    in_mesh = tmp_path / "cube.obj"
    cube.export(str(in_mesh))

    invalid_marker = ReferenceMarker(marker_id=0, known_size_mm=-10.0)
    processor = ScalingProcessor()

    with pytest.raises(ScalingConfigError):
        processor.process(
            input_mesh_path=in_mesh,
            reference_marker=invalid_marker,
            reference_measurements=25.0,
            raise_on_error=True,
        )


def test_scaling_processor_end_to_end_colmap_triangulation(tmp_path: Path) -> None:
    """Verify ScalingProcessor end-to-end ArUco triangulation and affine mesh scaling from COLMAP."""
    cube = create_clean_cube()
    in_mesh = tmp_path / "cube.obj"
    cube.export(str(in_mesh))
    out_mesh = tmp_path / "scaled_cube.obj"

    colmap_dir, images_dir, expected_sfm_size = _setup_synthetic_colmap_scene(tmp_path)

    config = ScalingConfig(
        marker_id=0,
        marker_size_mm=50.0,
        dictionary="DICT_4X4_50",
    )
    processor = ScalingProcessor(config=config)

    # When reference_measurements is omitted, processor acquires 3D reference via COLMAP triangulation
    result = processor.process(
        input_mesh_path=in_mesh,
        output_mesh_path=out_mesh,
        colmap_dir=colmap_dir,
        images_dir=images_dir,
    )

    assert result.status == "SUCCESS"
    assert result.success is True
    assert result.measurement is not None
    assert result.measurement["measurement_count"] == 4
    # Expected scale = 50.0 / 0.1 = 500.0
    expected_scale = 50.0 / expected_sfm_size
    assert result.scale_factor == pytest.approx(expected_scale, rel=0.03)
    assert result.vertex_count_before == 8
    assert result.vertex_count_after == 8
    assert result.face_count_before == 12
    assert result.face_count_after == 12

    # Verify scaled mesh vertices transformed via affine matrix
    scaled_mesh = trimesh.load(str(out_mesh), process=False)
    # Cube original extent is 2.0x2.0x2.0 -> scaled extent is 2.0 * scale_factor
    expected_extents = [2.0 * result.scale_factor] * 3
    np.testing.assert_allclose(scaled_mesh.extents, expected_extents, rtol=1e-4)


def test_scaling_processor_configured_colmap_defaults(tmp_path: Path) -> None:
    """Verify ScalingProcessor uses colmap_dir and images_dir from ScalingConfig."""
    cube = create_clean_cube()
    in_mesh = tmp_path / "cube.obj"
    cube.export(str(in_mesh))
    out_mesh = tmp_path / "scaled_cube.obj"

    colmap_dir, images_dir, expected_sfm_size = _setup_synthetic_colmap_scene(tmp_path)

    config = ScalingConfig(
        marker_id=0,
        marker_size_mm=100.0,
        dictionary="DICT_4X4_50",
        colmap_dir=colmap_dir,
        images_dir=images_dir,
    )
    processor = ScalingProcessor(config=config)

    result = processor.process(
        input_mesh_path=in_mesh,
        output_mesh_path=out_mesh,
    )

    assert result.status == "SUCCESS"
    assert result.scale_factor == pytest.approx(100.0 / expected_sfm_size, rel=0.03)
    assert out_mesh.is_file()


def test_scaling_processor_aruco_graceful_fallback_insufficient_views(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify ScalingProcessor gracefully falls back when ArUco marker is observed in < 2 images."""
    import logging
    from unittest.mock import patch
    from loom.scaling.aruco import ArucoDetector
    from loom.scaling.exceptions import ReferenceDetectionError

    cube = create_clean_cube()
    in_mesh = tmp_path / "cube.obj"
    cube.export(str(in_mesh))
    out_mesh = tmp_path / "unscaled_fallback.obj"

    config = ScalingConfig(
        marker_id=0,
        marker_size_mm=50.0,
        dictionary="DICT_4X4_50",
    )
    processor = ScalingProcessor(config=config)

    with caplog.at_level(logging.WARNING), patch.object(
        ArucoDetector,
        "compute_reconstructed_marker_size",
        side_effect=ReferenceDetectionError("Marker ID 0 was observed in 1 images (< 2 required for triangulation)."),
    ):
        result = processor.process(
            input_mesh_path=in_mesh,
            output_mesh_path=out_mesh,
            colmap_dir=tmp_path / "sparse",
            images_dir=tmp_path / "images",
            raise_on_error=False,
        )

    assert result.status == "SKIPPED"
    assert result.success is False
    assert result.scale_factor == 1.0
    assert out_mesh.is_file()
    assert "ArUco marker not observed in registered views" in caplog.text

