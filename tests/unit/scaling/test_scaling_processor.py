"""Unit tests for ScalingProcessor pipeline orchestration and error handling."""

from __future__ import annotations

from pathlib import Path
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
