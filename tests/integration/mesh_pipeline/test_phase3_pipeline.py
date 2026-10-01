"""Integration tests for Phase 3 Mesh Pipeline and CLI integration."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import pytest

from loom.config.models import LoomConfig, MeshConfig
from loom.mesh.models import MeshProcessingResult
from loom.pipeline.runner import run_phase3_mesh_pipeline
from tests.fixtures.mesh_fixtures import (
    create_clean_cube,
    create_disconnected_mesh,
    create_hole_mesh,
    save_fixture_mesh,
)


def test_phase3_standalone_pipeline_clean_cube(tmp_path: Path) -> None:
    """Verify run_phase3_mesh_pipeline execution on clean cube fixture."""
    cube = create_clean_cube()
    mesh_path = save_fixture_mesh(cube, tmp_path / "raw.obj")
    output_dir = tmp_path / "runs"

    config = LoomConfig(output_dir=output_dir)
    result, report_path = run_phase3_mesh_pipeline(mesh_path, config=config)

    assert result.success is True
    assert result.output_mesh_path is not None
    assert result.output_mesh_path.exists()
    assert result.vertex_count_after == 8
    assert result.face_count_after == 12

    # Check directory structure
    # run directory should contain geometry/ and reports/
    run_dir = result.output_mesh_path.parent.parent
    assert (run_dir / "geometry").exists()
    assert (run_dir / "reports").exists()

    report_json_path = run_dir / "reports" / "geometry.json"
    assert report_json_path.exists()
    assert report_path == report_json_path

    with open(report_json_path, "r", encoding="utf-8") as f:
        report_data = json.load(f)

    assert report_data["success"] is True
    assert report_data["status"] == "SUCCESS"
    assert report_data["vertex_count_before"] == 8
    assert report_data["vertex_count_after"] == 8
    assert "diagnostics_before" in report_data
    assert "diagnostics_after" in report_data


def test_phase3_standalone_pipeline_disconnected_mesh(tmp_path: Path) -> None:
    """Verify run_phase3_mesh_pipeline removes disconnected component."""
    mesh = create_disconnected_mesh()
    mesh_path = save_fixture_mesh(mesh, tmp_path / "disconnected.ply", "ply")
    output_dir = tmp_path / "runs"

    config = LoomConfig(
        output_dir=output_dir,
        mesh=MeshConfig(component_strategy="largest"),
    )
    result, report_path = run_phase3_mesh_pipeline(mesh_path, config=config)

    assert result.success is True
    assert result.component_count_before == 2
    assert result.component_count_after == 1
    assert result.removed_components == 1
    assert result.face_count_after == 12



def test_phase3_cli_geometry_subcommand(tmp_path: Path) -> None:
    """Verify CLI execution via: python -m loom geometry --input <mesh>."""
    cube = create_clean_cube()
    mesh_path = save_fixture_mesh(cube, tmp_path / "raw.obj")
    output_dir = tmp_path / "cli_runs"

    cmd = [
        sys.executable,
        "-m",
        "loom",
        "geometry",
        "--input",
        str(mesh_path),
        "--output-dir",
        str(output_dir),
    ]

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, f"CLI stdout: {proc.stdout}\nstderr: {proc.stderr}"
    assert "LOOM GEOMETRY PROCESSING" in proc.stdout
    assert "cleaned_raw.obj" in proc.stdout
    assert "geometry.json" in proc.stdout



def test_phase3_cli_mesh_flag(tmp_path: Path) -> None:
    """Verify CLI execution via: python -m loom --mesh <mesh>."""
    mesh = create_hole_mesh()
    mesh_path = save_fixture_mesh(mesh, tmp_path / "hole.obj")
    output_dir = tmp_path / "cli_mesh_runs"

    cmd = [
        sys.executable,
        "-m",
        "loom",
        "--mesh",
        str(mesh_path),
        "--output-dir",
        str(output_dir),
    ]

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, f"CLI stdout: {proc.stdout}\nstderr: {proc.stderr}"
    assert "LOOM GEOMETRY PROCESSING" in proc.stdout
    assert "SUCCESS" in proc.stdout


def test_phase3_cli_nonexistent_file_exits_error(tmp_path: Path) -> None:
    """Verify CLI exits with non-zero code on nonexistent input mesh."""
    cmd = [
        sys.executable,
        "-m",
        "loom",
        "geometry",
        "--input",
        str(tmp_path / "nonexistent.obj"),
    ]

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode != 0
