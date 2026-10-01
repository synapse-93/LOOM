"""Unit tests for MeshProcessor orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pytest

from loom.config.models import MeshConfig
from loom.mesh.exceptions import (
    MeshFormatError,
    MeshInvalidError,
    MeshLoadError,
)
from loom.mesh.processor import MeshProcessor
from tests.fixtures.mesh_fixtures import (
    create_clean_cube,
    create_disconnected_mesh,
    create_degenerate_mesh,
    create_hole_mesh,
    save_fixture_mesh,
)


def test_process_clean_cube(tmp_path: Path) -> None:
    """Verify end-to-end processing of a clean watertight cube."""
    cube = create_clean_cube()
    input_path = save_fixture_mesh(cube, tmp_path / "cube.obj")
    output_path = tmp_path / "output" / "cleaned_cube.obj"

    processor = MeshProcessor(MeshConfig())
    result = processor.process(input_path, output_path)

    assert result.success is True
    assert result.output_mesh_path == output_path
    assert output_path.exists()
    assert result.vertex_count_after == 8
    assert result.face_count_after == 12
    assert result.component_count_after == 1
    assert result.after_diagnostics.is_watertight is True
    assert result.processing_time_s > 0
    assert len(result.stages_completed) == 8


def test_process_disconnected_mesh(tmp_path: Path) -> None:
    """Verify end-to-end component filtering on a disconnected mesh."""
    mesh = create_disconnected_mesh()
    input_path = save_fixture_mesh(mesh, tmp_path / "disconnected.ply", "ply")
    output_path = tmp_path / "output" / "cleaned.ply"

    processor = MeshProcessor(MeshConfig(component_strategy="largest"))
    result = processor.process(input_path, output_path)

    assert result.success is True
    assert result.component_count_before == 2
    assert result.component_count_after == 1
    assert result.removed_components == 1
    assert result.face_count_after == 12
    assert result.vertex_count_after == 8


def test_process_degenerate_mesh(tmp_path: Path) -> None:
    """Verify end-to-end degenerate face removal."""
    mesh = create_degenerate_mesh()
    input_path = save_fixture_mesh(mesh, tmp_path / "degenerate.obj")
    output_path = tmp_path / "output" / "cleaned.obj"

    processor = MeshProcessor(MeshConfig(remove_degenerate_faces=True))
    result = processor.process(input_path, output_path)

    assert result.success is True
    assert result.degenerate_faces_before >= 1
    assert result.degenerate_faces_removed >= 1
    assert result.face_count_after == 12


def test_process_hole_mesh(tmp_path: Path) -> None:
    """Verify end-to-end hole repair."""
    mesh = create_hole_mesh()
    input_path = save_fixture_mesh(mesh, tmp_path / "hole.stl", "stl")
    output_path = tmp_path / "output" / "cleaned.stl"

    processor = MeshProcessor(MeshConfig(fill_holes=True, max_hole_edges=30))
    result = processor.process(input_path, output_path)

    assert result.success is True
    assert result.boundary_defects_before >= 1
    assert result.repairs_attempted >= 1
    assert result.repairs_successful >= 1
    assert result.remaining_boundary_defects == 0
    assert result.after_diagnostics.is_watertight is True


def test_process_preserves_coordinates_and_scale(tmp_path: Path) -> None:
    """Verify mesh normalization preserves exact physical coordinates and does NOT center/scale."""
    cube = create_clean_cube()
    # Translate vertices far from origin
    cube.vertices += np.array([100.0, 200.0, 300.0])
    orig_bounds = cube.bounds.copy()

    input_path = save_fixture_mesh(cube, tmp_path / "offset_cube.obj")
    output_path = tmp_path / "output" / "offset_cleaned.obj"

    processor = MeshProcessor(MeshConfig())
    result = processor.process(input_path, output_path)

    assert result.success is True
    assert np.allclose(result.before_diagnostics.bounding_box["min"], orig_bounds[0])
    assert np.allclose(result.after_diagnostics.bounding_box["min"], orig_bounds[0])
    assert np.allclose(result.before_diagnostics.extents, [2.0, 2.0, 2.0])
    assert np.allclose(result.after_diagnostics.extents, [2.0, 2.0, 2.0])


def test_process_missing_file_raises(tmp_path: Path) -> None:
    """Verify nonexistent input mesh raises FileNotFoundError."""
    processor = MeshProcessor(MeshConfig())
    with pytest.raises(FileNotFoundError):
        processor.process(tmp_path / "nonexistent.obj")


def test_process_directory_input_raises(tmp_path: Path) -> None:
    """Verify directory input raises MeshInvalidError."""
    processor = MeshProcessor(MeshConfig())
    with pytest.raises(MeshInvalidError):
        processor.process(tmp_path)


def test_process_unsupported_format_raises(tmp_path: Path) -> None:
    """Verify unsupported file format raises MeshFormatError."""
    p = tmp_path / "mesh.xyz"
    p.write_text("1 2 3", encoding="utf-8")
    processor = MeshProcessor(MeshConfig())
    with pytest.raises(MeshFormatError):
        processor.process(p)


def test_process_empty_file_raises(tmp_path: Path) -> None:
    """Verify empty file raises MeshInvalidError."""
    p = tmp_path / "empty.obj"
    p.touch()
    processor = MeshProcessor(MeshConfig())
    with pytest.raises(MeshInvalidError):
        processor.process(p)


def test_process_corrupt_file_raises(tmp_path: Path) -> None:
    """Verify corrupt mesh file raises MeshLoadError."""
    p = tmp_path / "corrupt.obj"
    p.write_text("NOT A VALID OBJ FILE\nFOOBAR BAZ\n", encoding="utf-8")
    processor = MeshProcessor(MeshConfig())
    with pytest.raises((MeshLoadError, MeshInvalidError)):
        processor.process(p)



def test_process_result_to_dict_and_json(tmp_path: Path) -> None:
    """Verify result serializes cleanly to dict and valid JSON."""
    cube = create_clean_cube()
    input_path = save_fixture_mesh(cube, tmp_path / "cube.obj")
    output_path = tmp_path / "cleaned.obj"

    processor = MeshProcessor(MeshConfig())
    result = processor.process(input_path, output_path)

    d = result.to_dict()
    assert isinstance(d, dict)
    assert d["success"] is True
    assert d["vertex_count_after"] == 8

    # Must be serializable by standard json.dumps
    json_str = json.dumps(d)
    assert isinstance(json_str, str)
    parsed = json.loads(json_str)
    assert parsed["success"] is True
