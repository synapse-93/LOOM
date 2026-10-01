"""Comprehensive unit and audit tests for realistic photogrammetry mesh processing (Phase 3).

Audits behavior against realistic photogrammetry artifacts:
- Complex multi-faceted surface (>1000 faces)
- Non-origin arbitrary SfM coordinate frame
- Open unobserved base boundary (>30 edges)
- Small repairable pinhole/gap (3 edges)
- Floating disconnected background noise clusters ("dust")
- Zero-area degenerate sliver triangles
- Duplicate faces and unreferenced vertices
"""

from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pytest
import trimesh

from loom.config.models import LoomConfig, MeshConfig
from loom.mesh.cleanup import MeshCleaner
from loom.mesh.components import MeshComponentAnalyzer
from loom.mesh.diagnostics import MeshDiagnostics
from loom.mesh.processor import MeshProcessor
from loom.mesh.repair import MeshRepairer
from tests.fixtures.mesh_fixtures import create_photogrammetry_raw_mesh, save_fixture_mesh


def test_photogrammetry_raw_mesh_diagnostics() -> None:
    """Verify that read-only diagnostics accurately characterize photogrammetric mesh flaws."""
    offset = (105.4, 42.1, -210.8)
    mesh = create_photogrammetry_raw_mesh(radius=10.0, offset=offset)

    diag = MeshDiagnostics.inspect(mesh)

    assert diag.vertex_count > 500
    assert diag.face_count > 1000
    assert diag.component_count >= 3  # Main body + 2 satellite noise clusters
    assert diag.boundary_loop_count >= 2  # 1 small hole + 1 large open base
    assert diag.duplicate_face_count >= 1
    assert diag.unreferenced_vertex_count >= 3
    assert diag.status == "WARNING"

    # Verify bounding box reflects the arbitrary SfM coordinate offset
    bb_min = diag.bounding_box_min
    bb_max = diag.bounding_box_max
    center = [(a + b) / 2.0 for a, b in zip(bb_min, bb_max)]
    assert np.isclose(center[0], offset[0], atol=30.0)
    assert np.isclose(center[1], offset[1], atol=30.0)
    assert np.isclose(center[2], offset[2], atol=30.0)


def test_photogrammetry_component_filtering() -> None:
    """Verify component filtering isolates dominant object and prunes photogrammetry dust."""
    mesh = create_photogrammetry_raw_mesh(radius=10.0)
    cfg = MeshConfig(component_strategy="largest")

    filtered, action = MeshComponentAnalyzer.filter(mesh, cfg)

    assert action.components_before >= 3
    assert action.components_after == 1
    assert action.removed_components >= 2
    assert len(filtered.faces) < len(mesh.faces)
    assert len(filtered.faces) > 1000  # Main body retained


def test_photogrammetry_cleanup_removes_degeneracies() -> None:
    """Verify cleanup purges zero-area slivers, duplicates, and orphans without geometry loss."""
    mesh = create_photogrammetry_raw_mesh(radius=10.0)
    cfg = MeshConfig(
        remove_degenerate_faces=True,
        remove_duplicate_faces=True,
        remove_unreferenced_vertices=True,
        degenerate_area_threshold=1e-7,
    )

    cleaned, action = MeshCleaner.clean(mesh, cfg)

    assert action.duplicate_faces_removed >= 1
    assert action.unreferenced_vertices_removed >= 3
    assert action.faces_after < action.faces_before
    assert action.vertices_after < action.vertices_before


def test_photogrammetry_conservative_hole_repair() -> None:
    """Verify small pinhole is repaired while large open ground boundary is honestly preserved."""
    mesh = create_photogrammetry_raw_mesh(radius=10.0)
    # Default max_hole_edges=30: 3-edge hole is eligible, 40-edge open base is ineligible
    cfg = MeshConfig(close_holes=True, max_hole_edges=30, unify_normals=True)

    repaired, action = MeshRepairer.repair(mesh, cfg)

    assert action.repairs_attempted >= 1
    assert action.repairs_successful >= 1
    assert action.remaining_boundary_loops >= 1  # Open base remains open
    assert action.normals_unified is True

    # Inspect defect details to verify honesty in reporting
    statuses = [d["status"] for d in action.defect_details]
    assert "REPAIRED" in statuses
    assert "UNREPAIRED" in statuses


def test_photogrammetry_scale_and_coordinate_preservation(tmp_path: Path) -> None:
    """Verify that processing preserves raw SfM coordinates and does NOT center or rescale."""
    offset = (150.25, -75.50, 320.10)
    mesh = create_photogrammetry_raw_mesh(radius=10.0, offset=offset)

    input_path = save_fixture_mesh(mesh, tmp_path / "raw_sfm.obj")
    output_path = tmp_path / "cleaned_sfm.obj"

    processor = MeshProcessor(MeshConfig())
    result = processor.process(input_path, output_path)

    assert result.success is True

    # Compare bounding box bounds before and after
    bb_before = result.diagnostics_before.bounding_box_min
    bb_after = result.diagnostics_after.bounding_box_min

    # Coordinates must match closely (small variation from removed satellite components)
    assert np.isclose(bb_before[0], bb_after[0], atol=15.0)
    assert np.isclose(bb_before[1], bb_after[1], atol=15.0)
    assert np.isclose(bb_before[2], bb_after[2], atol=15.0)

    # Must NOT be centered at origin (0, 0, 0)
    assert abs(bb_after[0]) > 50.0
    assert abs(bb_after[2]) > 200.0


def test_photogrammetry_full_pipeline_and_json_report(tmp_path: Path) -> None:
    """Verify end-to-end processing and valid JSON report generation on realistic raw mesh."""
    mesh = create_photogrammetry_raw_mesh(radius=10.0)
    input_path = save_fixture_mesh(mesh, tmp_path / "photogrammetry_raw.obj")
    output_path = tmp_path / "output" / "cleaned_photogrammetry.obj"

    processor = MeshProcessor(MeshConfig())
    result = processor.process(input_path, output_path)

    assert result.success is True
    assert output_path.is_file()
    assert output_path.stat().st_size > 0

    # Cleaned mesh loads validly
    cleaned_loaded = trimesh.load(output_path, process=False)
    assert len(cleaned_loaded.faces) > 1000
    assert len(cleaned_loaded.vertices) > 500

    # Verify JSON serializability
    result_dict = result.to_dict()
    json_str = json.dumps(result_dict, indent=2)
    assert len(json_str) > 0
    parsed = json.loads(json_str)

    assert parsed["success"] is True
    assert parsed["vertex_count_before"] > parsed["vertex_count_after"]
    assert parsed["face_count_before"] > parsed["face_count_after"]
    assert parsed["repairs_successful"] >= 1
    assert parsed["remaining_boundary_defects"] >= 1
    assert "diagnostics_before" in parsed
    assert "diagnostics_after" in parsed
    assert "cleanup" in parsed["actions"]
    assert "components" in parsed["actions"]
    assert "repair" in parsed["actions"]
