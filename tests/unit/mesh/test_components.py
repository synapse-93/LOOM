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
