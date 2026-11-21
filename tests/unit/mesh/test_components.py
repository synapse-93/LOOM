"""Unit tests for MeshComponentAnalyzer."""

from __future__ import annotations

import pytest
import trimesh

from loom.config.models import MeshConfig
from loom.mesh.components import MeshComponentAnalyzer
from tests.fixtures.mesh_fixtures import create_clean_cube, create_disconnected_mesh


def test_analyze_single_component() -> None:
    """Verify single-component mesh analysis."""
    mesh = create_clean_cube()
    analyzer = MeshComponentAnalyzer(MeshConfig())
    components = analyzer.analyze_components(mesh)

    assert len(components) == 1
    assert components[0].component_id == 0
    assert components[0].face_count == 12
    assert components[0].vertex_count == 8


def test_analyze_disconnected_components() -> None:
    """Verify multi-component mesh detection."""
    mesh = create_disconnected_mesh()
    analyzer = MeshComponentAnalyzer(MeshConfig())
    components = analyzer.analyze_components(mesh)

    assert len(components) == 2
    # Sorted by face count descending
    assert components[0].face_count == 12
    assert components[1].face_count == 4


def test_filter_strategy_largest() -> None:
    """Verify 'largest' strategy keeps only the primary component."""
    mesh = create_disconnected_mesh()
    config = MeshConfig(component_strategy="largest")
    analyzer = MeshComponentAnalyzer(config)

    cleaned_mesh, action = analyzer.filter_components(mesh)

    assert action.strategy == "largest"
    assert action.components_before == 2
    assert action.components_after == 1
    assert action.removed_components == 1
    assert action.removed_faces == 4
    assert len(cleaned_mesh.faces) == 12
    assert len(cleaned_mesh.vertices) == 8


def test_filter_strategy_min_faces() -> None:
    """Verify 'min_faces' strategy filters components below threshold."""
    mesh = create_disconnected_mesh()
    # Threshold 10 faces keeps the cube (12) and drops the tet (4)
    config = MeshConfig(component_strategy="min_faces", min_component_faces=10)
    analyzer = MeshComponentAnalyzer(config)

    cleaned_mesh, action = analyzer.filter_components(mesh)

    assert action.components_before == 2
    assert action.components_after == 1
    assert action.removed_components == 1
    assert len(cleaned_mesh.faces) == 12


def test_filter_strategy_relative_threshold() -> None:
    """Verify 'relative_threshold' strategy filters components smaller than a fraction of largest."""
    mesh = create_disconnected_mesh()
    # 4/12 = 0.33. If threshold is 0.5, the 4-face component should be dropped.
    config = MeshConfig(component_strategy="relative_threshold", min_component_ratio=0.5)
    analyzer = MeshComponentAnalyzer(config)

    cleaned_mesh, action = analyzer.filter_components(mesh)

    assert action.components_before == 2
    assert action.components_after == 1
    assert action.removed_components == 1
    assert len(cleaned_mesh.faces) == 12


def test_filter_strategy_keep_all() -> None:
    """Verify 'keep_all' strategy retains all components unchanged."""
    mesh = create_disconnected_mesh()
    config = MeshConfig(component_strategy="keep_all")
    analyzer = MeshComponentAnalyzer(config)

    cleaned_mesh, action = analyzer.filter_components(mesh)

    assert action.components_before == 2
    assert action.components_after == 2
    assert action.removed_components == 0
    assert len(cleaned_mesh.faces) == 16


def test_get_face_components_returns_sorted_face_arrays() -> None:
    """Verify get_face_components returns index arrays sorted descending by face count."""
    mesh = create_disconnected_mesh()  # 12-face cube + 4-face tet
    face_comps = MeshComponentAnalyzer.get_face_components(mesh)

    assert len(face_comps) == 2
    assert len(face_comps[0]) == 12
    assert len(face_comps[1]) == 4


def test_filter_strategy_centroid_proximity_default_component_zero() -> None:
    """Verify when reference_point is None, Component #0 is directly selected."""
    mesh = create_disconnected_mesh()
    cfg = MeshConfig(component_strategy="centroid_proximity", reference_point=None)
    filtered, action = MeshComponentAnalyzer.filter(mesh, cfg)

    assert action.strategy == "centroid_proximity"
    assert len(filtered.faces) == 12


def test_filter_strategy_centroid_proximity_rejects_speck_when_large_component_exists() -> None:
    """Verify that when large components exist, noise specks (< 1,000 faces) are strictly rejected."""
    # Synthetic mesh with 1 large component (10,000 faces) and 1 speck (50 faces)
    large_sphere = trimesh.creation.icosphere(subdivisions=4, radius=5.0)  # 5,120 faces
    # Duplicate to create > 10,000 total faces
    large_part2 = trimesh.creation.icosphere(subdivisions=4, radius=5.0)
    large_mesh = trimesh.util.concatenate([large_sphere, large_part2])  # 10,240 faces in 2 parts or 1 component if combined
    speck = trimesh.creation.icosphere(subdivisions=1, radius=0.1)  # 80 faces (< 1,000)
    speck.vertices += [0.0, 0.0, 0.0]  # Centered at (0, 0, 0)
    large_mesh.vertices += [50.0, 50.0, 0.0]  # Centered far away

    scene = trimesh.util.concatenate([large_mesh, speck])
    # Target reference point directly at speck (0, 0, 0)
    cfg = MeshConfig(
        component_strategy="centroid_proximity",
        reference_point=(0.0, 0.0, 0.0),
        min_component_faces=20,
    )
    filtered, action = MeshComponentAnalyzer.filter(scene, cfg)

    # Speck (< 1,000 faces) must be rejected because large component exists
    assert len(filtered.faces) > 1000
    assert len(filtered.faces) != len(speck.faces)
