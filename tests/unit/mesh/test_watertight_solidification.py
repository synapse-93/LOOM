"""Unit tests for Phase 4 Taubin polish, guaranteed watertight solidification, and metric scaling."""

from __future__ import annotations

import numpy as np
import trimesh

from loom.mesh.processor import MeshProcessor
from loom.printability.gate import PrintabilityGate


def _make_open_bottom_and_side_hole_box() -> trimesh.Trimesh:
    """Create a subdivided box with its bottom face removed and a side-wall cutout hole."""
    box = trimesh.creation.box(extents=[1.2, 0.8, 1.0])
    # Subdivide twice so removing a wall patch creates a realistic multi-edge wall void
    sub = box.subdivide().subdivide()
    verts = np.asarray(sub.vertices, dtype=np.float64)
    faces = np.asarray(sub.faces, dtype=np.int64)
    centers = verts[faces].mean(axis=1)
    normals = np.asarray(sub.face_normals, dtype=np.float64)

    # Remove entire bottom face (z near -0.5, pointing down)
    is_bottom = (centers[:, 2] < -0.49) & (normals[:, 2] < -0.5)
    # Remove a patch in the center of the +X side wall (creates a real side-wall void)
    is_side_hole = (
        (centers[:, 0] > 0.59)
        & (np.abs(centers[:, 1]) < 0.22)
        & (np.abs(centers[:, 2]) < 0.22)
    )
    keep = ~(is_bottom | is_side_hole)
    damaged = trimesh.Trimesh(vertices=verts, faces=faces[keep], process=False)
    damaged.remove_unreferenced_vertices()
    assert not damaged.is_watertight
    return damaged


def test_solidify_for_print_closes_open_bottom_and_side_hole_box() -> None:
    """Synthetic open-bottom + side-hole box must become watertight, positive-volume, Z_min=0, and scaled."""
    damaged = _make_open_bottom_and_side_hole_box()
    target_mm = 200.0

    res = MeshProcessor.solidify_for_print(
        damaged,
        target_length_mm=target_mm,
        taubin_iterations=3,
        poisson_depth=7,
    )

    assert res.validation_passed is True
    assert res.is_watertight is True
    assert res.is_manifold is True
    assert res.is_winding_consistent is True
    assert res.volume_mm3 > 0.0
    assert res.solidification_method in ("planar_cap", "hole_fill", "voxel_remesh")
    assert abs(res.z_min_mm) < 1e-4
    assert abs(max(res.extents_mm) - target_mm) < 0.1

    # Double-check independently via PrintabilityGate
    gate_res = PrintabilityGate().validate(res.mesh)
    assert gate_res.passed is True
    assert gate_res.boundary_edge_count == 0
    assert gate_res.non_manifold_edge_count == 0
    assert gate_res.non_manifold_vertex_count == 0
    assert gate_res.volume_mm3 > 0.0
    assert abs(float(res.mesh.bounds[0][2])) < 1e-4


def test_solidify_for_print_planar_cap_fast_path_on_open_bottom_cylinder() -> None:
    """An open-bottom cylinder with no side holes should close cleanly via planar_cap (mapbox-earcut)."""
    cyl = trimesh.creation.cylinder(radius=0.4, height=1.2, sections=48)
    centers = cyl.triangles_center
    normals = cyl.face_normals
    keep = ~((centers[:, 2] < -0.59) & (normals[:, 2] < -0.5))
    open_cyl = trimesh.Trimesh(vertices=cyl.vertices.copy(), faces=cyl.faces[keep].copy(), process=False)
    open_cyl.remove_unreferenced_vertices()
    assert not open_cyl.is_watertight

    res = MeshProcessor.solidify_for_print(
        open_cyl,
        target_length_mm=150.0,
        taubin_iterations=2,
    )

    assert res.validation_passed is True
    assert res.is_watertight is True
    assert res.volume_mm3 > 0.0
    assert res.solidification_method in ("planar_cap", "hole_fill")
    assert abs(res.z_min_mm) < 1e-4
    assert abs(max(res.extents_mm) - 150.0) < 0.1

