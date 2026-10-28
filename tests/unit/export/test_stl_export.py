"""Unit tests for STL model exporter."""

from __future__ import annotations

from pathlib import Path

import pytest
import trimesh

from loom.export.stl import StlExporter


def test_stl_export_binary_cube(tmp_path: Path) -> None:
    mesh_path = tmp_path / "cube.obj"
    cube = trimesh.creation.box(extents=[10.0, 20.0, 30.0])
    cube.export(mesh_path)

    out_stl = tmp_path / "cube.stl"
    exporter = StlExporter()
    exported_path = exporter.export(mesh_path, out_stl, binary=True)

    assert exported_path == out_stl
    assert out_stl.is_file()
    assert out_stl.stat().st_size > 0

    reloaded = trimesh.load(out_stl, force="mesh")
    assert len(reloaded.vertices) > 0
    assert len(reloaded.faces) > 0


def test_stl_export_ascii_cube(tmp_path: Path) -> None:
    mesh_path = tmp_path / "cube.obj"
    cube = trimesh.creation.box(extents=[5.0, 5.0, 5.0])
    cube.export(mesh_path)

    out_stl = tmp_path / "cube_ascii.stl"
    exporter = StlExporter()
    exported_path = exporter.export(mesh_path, out_stl, binary=False)

    assert exported_path == out_stl
    assert out_stl.is_file()
    header = out_stl.read_text(encoding="ascii", errors="ignore")
    assert "solid" in header


def test_stl_export_missing_file_raises(tmp_path: Path) -> None:
    exporter = StlExporter()
    with pytest.raises(FileNotFoundError):
        exporter.export(tmp_path / "nonexistent.obj", tmp_path / "out.stl")


def test_stl_export_empty_mesh_raises(tmp_path: Path) -> None:
    empty_mesh_path = tmp_path / "empty.obj"
    empty_mesh_path.write_text("# Empty obj\n")

    exporter = StlExporter()
    with pytest.raises(ValueError):
        exporter.export(empty_mesh_path, tmp_path / "out.stl")
