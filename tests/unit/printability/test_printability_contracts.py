
"""Tests for printability verification and report generation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import trimesh

from loom.printability.manifold import ManifoldChecker
from loom.printability.report import (
    PrintabilityReport,
    PrintabilityReportGenerator,
)
from loom.printability.thickness import WallThicknessAnalyzer
from loom.printability.watertight import WatertightChecker


def test_printability_report_export(tmp_path: Path) -> None:
    """Verify PrintabilityReport JSON serialization."""
    report = PrintabilityReport(
        is_watertight=True,
        is_manifold=True,
        min_wall_thickness_mm=1.5,
        overhang_face_count=12,
        is_printable=True,
        warnings=[],
    )

    out_file = tmp_path / "print_report.json"
    PrintabilityReportGenerator.export_json(report, out_file)

    assert out_file.is_file()

    with open(out_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["is_watertight"] is True
    assert data["min_wall_thickness_mm"] == 1.5


def test_manifold_checker_rejects_missing_file() -> None:
    """Verify the manifold checker rejects a missing mesh file."""
    checker = ManifoldChecker()

    with pytest.raises(FileNotFoundError):
        checker.is_edge_manifold(Path("mesh.obj"))


def test_watertight_checker_rejects_missing_file() -> None:
    """Verify the watertight checker rejects a missing mesh file."""
    checker = WatertightChecker()

    with pytest.raises(FileNotFoundError):
        checker.is_watertight(Path("mesh.obj"))


def test_cube_is_watertight_and_manifold(tmp_path: Path) -> None:
    """A closed cube should pass the basic mesh checks."""
    mesh_path = tmp_path / "cube.obj"
    trimesh.creation.box().export(mesh_path)

    assert WatertightChecker().is_watertight(mesh_path)
    assert ManifoldChecker().is_edge_manifold(mesh_path)
    assert ManifoldChecker().is_vertex_manifold(mesh_path)


def test_open_mesh_is_not_watertight(tmp_path: Path) -> None:
    """A cube with one face removed should not be watertight."""
    mesh_path = tmp_path / "open_cube.obj"
    mesh = trimesh.creation.box()
    mesh.update_faces(range(len(mesh.faces) - 1))
    mesh.export(mesh_path)

    assert not WatertightChecker().is_watertight(mesh_path)


def test_cube_minimum_thickness_estimate(tmp_path: Path) -> None:
    """A 10-unit cube should yield a finite, positive thickness estimate."""
    mesh_path = tmp_path / "cube.obj"
    trimesh.creation.box(extents=[10, 10, 10]).export(mesh_path)

    thickness = WallThicknessAnalyzer().compute_minimum_thickness(mesh_path)

    assert thickness > 0
    assert thickness == pytest.approx(10.0, abs=0.1)


def test_thickness_analyzer_rejects_missing_file() -> None:
    """A missing mesh should raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        WallThicknessAnalyzer().compute_minimum_thickness(Path("missing.obj"))
