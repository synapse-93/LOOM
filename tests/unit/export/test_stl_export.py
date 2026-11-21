"""Unit tests for StlExporter binary STL generation, printability gate, and manifest generation."""

from __future__ import annotations

import json
from pathlib import Path
import struct
import pytest
import trimesh

from loom.config.models import ExportConfig
from loom.export.stl import StlExporter
from loom.printability.exceptions import PrintabilityValidationError
from tests.fixtures.mesh_fixtures import create_clean_cube


def _create_open_cube() -> trimesh.Trimesh:
    """Create a cube missing one face (open boundary)."""
    cube = create_clean_cube()
    return trimesh.Trimesh(vertices=cube.vertices, faces=cube.faces[1:], process=False)


def test_stl_export_valid_mesh(tmp_path: Path) -> None:
    """Verify StlExporter produces valid binary STL and JSON manifest with dimensions, volume, and triangle count."""
    cube = create_clean_cube()
    input_mesh = tmp_path / "shoe_model.obj"
    cube.export(str(input_mesh))

    export_dir = tmp_path / "outputs" / "stl"
    config = ExportConfig(output_dir=export_dir)
    exporter = StlExporter(config=config, enforce_printability_gate=True)

    # Export to default destination outputs/stl/<model_name>_metric.stl
    exported_stl = exporter.export(input_mesh)

    # 1. Verify STL file output path and naming
    assert exported_stl.is_file()
    assert exported_stl.name == "shoe_model_metric.stl"
    assert exported_stl.parent == export_dir.resolve()

    # 2. Verify binary STL header and structure
    data = exported_stl.read_bytes()
    assert len(data) >= 84
    # Unpack uint32 triangle count at byte offset 80
    tri_count = struct.unpack("<I", data[80:84])[0]
    assert tri_count == len(cube.faces)
    # Expected binary STL size: 80 bytes header + 4 bytes count + 50 bytes per triangle
    expected_size = 84 + tri_count * 50
    assert len(data) == expected_size

    # 3. Verify JSON manifest contents
    manifest_path = exported_stl.parent / f"{exported_stl.stem}_manifest.json"
    assert manifest_path.is_file()

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)

    assert manifest_data["stl_filename"] == "shoe_model_metric.stl"
    assert manifest_data["triangle_count"] == len(cube.faces)
    assert manifest_data["volume_mm3"] == pytest.approx(8.0)
    assert manifest_data["is_watertight"] is True
    assert len(manifest_data["bounding_box_mm"]) == 3
    assert manifest_data["bounding_box_mm"][0] == pytest.approx(2.0, abs=0.1)
    assert manifest_data["bounding_box_mm"][1] == pytest.approx(2.0, abs=0.1)
    assert manifest_data["bounding_box_mm"][2] == pytest.approx(2.0, abs=0.1)
    assert manifest_data["file_sha256"] == exporter._compute_sha256(exported_stl)


def test_stl_export_enforces_printability_gate(tmp_path: Path) -> None:
    """Verify StlExporter rejects meshes that fail watertight or manifold gate criteria."""
    open_cube = _create_open_cube()
    in_mesh = tmp_path / "open_cube.obj"
    open_cube.export(str(in_mesh))

    export_dir = tmp_path / "outputs" / "stl"
    exporter = StlExporter(config=ExportConfig(output_dir=export_dir), enforce_printability_gate=True)

    # Gate enforcement must reject open mesh
    with pytest.raises(PrintabilityValidationError, match="open boundary edges"):
        exporter.export(in_mesh)

    # STL file must NOT have been written
    target_stl = export_dir / "open_cube_metric.stl"
    assert not target_stl.exists()

    # Bypassing gate explicitly allows export if needed for diagnostics
    bypassed_stl = exporter.export(in_mesh, enforce_gate=False)
    assert bypassed_stl.is_file()


def test_stl_export_custom_paths(tmp_path: Path) -> None:
    """Verify StlExporter respects explicit destination STL and manifest paths."""
    cube = create_clean_cube()
    in_mesh = tmp_path / "input.obj"
    cube.export(str(in_mesh))

    custom_stl = tmp_path / "custom_dir" / "custom_part.stl"
    custom_manifest = tmp_path / "custom_dir" / "part_manifest.json"

    exporter = StlExporter()
    out_stl = exporter.export(
        in_mesh,
        output_stl_path=custom_stl,
        manifest_path=custom_manifest,
    )

    assert out_stl == custom_stl.resolve()
    assert custom_stl.is_file()
    assert custom_manifest.is_file()

    with open(custom_manifest, "r", encoding="utf-8") as f:
        m = json.load(f)
    assert m["stl_filename"] == "custom_part.stl"
    assert m["triangle_count"] == 12

