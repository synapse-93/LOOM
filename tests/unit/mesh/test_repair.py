"""Unit tests for MeshRepairer (conservative defect and hole repair)."""

from __future__ import annotations

import numpy as np
import pytest
import trimesh

from loom.config.models import MeshConfig
from loom.mesh.repair import MeshRepairer
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
