"""Unit tests for MeshRepairer (conservative defect and hole repair)."""

from __future__ import annotations

import numpy as np
import pytest
import trimesh

from loom.config.models import MeshConfig
from loom.mesh.repair import MeshRepairer, split_into_simple_cycles
from tests.fixtures.mesh_fixtures import (
    create_clean_cube,
    create_hole_mesh,
    create_large_hole_mesh,
)


def test_repair_clean_mesh_no_action() -> None:
    """Verify clean mesh requires no repairs."""
    mesh = create_clean_cube()
    repairer = MeshRepairer(MeshConfig())
    repaired_mesh, action = repairer.repair_mesh(mesh)

    assert action.holes_detected == 0
    assert action.holes_eligible == 0
    assert action.holes_repaired == 0
    assert action.remaining_defects == 0
    assert action.faces_added == 0
    assert repaired_mesh.is_watertight is True


def test_repair_small_hole() -> None:
    """Verify small hole (3 edges) is detected, eligible, repaired, and restores watertightness."""
    mesh = create_hole_mesh()
    assert mesh.is_watertight is False
    assert len(mesh.faces) == 11

    repairer = MeshRepairer(MeshConfig(fill_holes=True, max_hole_edges=30))
    repaired_mesh, action = repairer.repair_mesh(mesh)

    assert action.holes_detected >= 1
    assert action.holes_eligible >= 1
    assert action.holes_repaired >= 1
    assert action.remaining_defects == 0
    assert action.faces_added >= 1
    assert len(repaired_mesh.faces) == 12
    assert repaired_mesh.is_watertight is True


def test_repair_large_hole_conservative_preservation() -> None:
    """Verify large hole (> max_hole_edges) is detected, declared ineligible, and left unrepaired."""
    # Cylinder rim with 32 boundary edges
    mesh = create_large_hole_mesh(32)
    initial_faces = len(mesh.faces)

    # Limit repair to max 20 edges
    config = MeshConfig(fill_holes=True, max_hole_edges=20)
    repairer = MeshRepairer(config)
    repaired_mesh, action = repairer.repair_mesh(mesh)

    assert action.holes_detected >= 1
    assert action.holes_eligible == 0  # Ineligible because 32 > 20
    assert action.holes_repaired == 0
    assert action.remaining_defects >= 1
    assert action.faces_added == 0
    assert any("exceeds" in d.get("reason", "").lower() for d in action.defect_details)



def test_unify_normals() -> None:
    """Verify normal unification on an inverted face."""
    mesh = create_clean_cube()
    # Invert the first face
    mesh.faces[0] = mesh.faces[0, ::-1]

    repairer = MeshRepairer(MeshConfig(unify_normals=True))
    repaired_mesh, action = repairer.repair_mesh(mesh)

    assert action.normals_unified is True
    assert repaired_mesh.is_watertight is True


def test_slice_and_cap_base_closed_box(tmp_path) -> None:
    """Verify planar base slicing and ear-clip capping produces a flat contact surface."""
    box = trimesh.creation.box(extents=(2.0, 2.0, 2.0))
    assert box.is_watertight is True
    assert np.isclose(box.bounds[0][2], -1.0)

    output_ply = tmp_path / "05_base_capped.ply"
    capped_mesh, stats = MeshRepairer.slice_and_cap_base(
        mesh=box,
        z_base=-0.5,
        output_path=output_ply,
    )

    assert stats["base_capped"] is True
    assert stats["boundary_loops_capped"] >= 1
    assert stats["is_watertight"] is True
    assert np.isclose(capped_mesh.bounds[0][2], -0.5)
    assert np.isclose(capped_mesh.bounds[1][2], 1.0)
    assert capped_mesh.volume > 0.0
    assert output_ply.is_file()
    assert output_ply.stat().st_size > 0


def test_slice_and_cap_base_open_mesh(tmp_path) -> None:
    """Verify base slicing and capping heals an open-bottom photogrammetric geometry."""
    # Cylinder with bottom cap deleted
    cylinder = trimesh.creation.cylinder(radius=1.0, height=2.0, sections=16)
    # Remove bottom faces
    bottom_faces = [i for i, f in enumerate(cylinder.faces) if np.all(cylinder.vertices[f][:, 2] <= -0.9)]
    cylinder.faces = np.delete(cylinder.faces, bottom_faces, axis=0)
    assert cylinder.is_watertight is False

    output_ply = tmp_path / "05_base_capped.ply"
    capped_mesh, stats = MeshRepairer.slice_and_cap_base(
        mesh=cylinder,
        z_base=-0.7,
        output_path=output_ply,
    )

    assert stats["base_capped"] is True
    assert stats["is_watertight"] is True
    assert np.isclose(capped_mesh.bounds[0][2], -0.7)
    assert output_ply.is_file()


def test_slice_and_cap_base_bottom_percentile() -> None:
    """Verify slicing using bottom_percentile calculation when z_base is omitted."""
    cone = trimesh.creation.cone(radius=1.0, height=2.0, sections=16)
    # Cone bounds: z in [-1.0, 1.0]
    z_min = cone.bounds[0][2]
    z_max = cone.bounds[1][2]
    percentile = 0.10
    expected_z = z_min + percentile * (z_max - z_min)

    capped_mesh, stats = MeshRepairer.slice_and_cap_base(
        mesh=cone,
        z_base=None,
        bottom_percentile=percentile,
    )

    assert stats["base_capped"] is True
    assert np.isclose(stats["z_base"], expected_z)
    assert np.isclose(capped_mesh.bounds[0][2], expected_z, atol=1e-3)
    assert capped_mesh.is_watertight is True


def test_split_into_simple_cycles() -> None:
    """Verify figure-8 pinch vertex loop is decomposed into disjoint simple cycles."""
    # Loop with a pinch vertex at 2: [0, 1, 2, 3, 4, 2, 5, 6]
    loop = [0, 1, 2, 3, 4, 2, 5, 6]
    cycles = split_into_simple_cycles(loop)

    assert len(cycles) == 2
    assert cycles[0] == [2, 3, 4]
    assert cycles[1] == [0, 1, 2, 5, 6]

    # Simple loop without pinches returns a single cycle
    simple_loop = [10, 11, 12, 13]
    simple_cycles = split_into_simple_cycles(simple_loop)
    assert len(simple_cycles) == 1
    assert simple_cycles[0] == [10, 11, 12, 13]


def test_reject_hole_filling_exceeding_perimeter_threshold() -> None:
    """Verify hole-filling rejects boundary loops exceeding 25% of total mesh bounding perimeter."""
    # Cylinder with top cap completely removed (a large open void)
    cylinder = trimesh.creation.cylinder(radius=1.0, height=2.0, sections=24)
    # Remove all top faces (z >= 0.9)
    top_faces = [i for i, f in enumerate(cylinder.faces) if np.all(cylinder.vertices[f][:, 2] >= 0.9)]
    cylinder.faces = np.delete(cylinder.faces, top_faces, axis=0)
    assert cylinder.is_watertight is False

    # Configure repair with close_all_holes=True
    cfg = MeshConfig(fill_holes=True, close_all_holes=True, max_hole_edges=100)
    repairer = MeshRepairer(cfg)
    repaired, action = repairer.repair_mesh(cylinder)

    # The top rim has radius 1.0 (perimeter = 2 * pi * 1.0 = ~6.28)
    # Cylinder bounds: extents = [2.0, 2.0, 2.0], total_bounding_perimeter = 2 * (2+2+2) = 12.0
    # 25% threshold = 3.0. Since 6.28 > 3.0, repair should be REJECTED to prevent starburst!
    assert action.holes_repaired == 0
    assert any("exceeds 25%" in d.get("reason", "").lower() for d in action.defect_details)
    assert repaired.is_watertight is False


