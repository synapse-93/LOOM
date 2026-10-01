"""Unit tests for Phase 4 scaling data models and serialization."""

from __future__ import annotations

import pytest
from loom.scaling.models import (
    MarkerObservation,
    ReferenceMarker,
    ReferenceMeasurement,
    ScaleEstimate,
    ScalingResult,
)


def test_reference_marker_model() -> None:
    """Test ReferenceMarker construction and dictionary serialization."""
    marker = ReferenceMarker(
        marker_type="aruco",
        marker_id=42,
        known_size_mm=75.5,
        dictionary="DICT_5X5_100",
    )
    d = marker.to_dict()
    assert d["marker_type"] == "aruco"
    assert d["marker_id"] == 42
    assert d["known_size_mm"] == 75.5
    assert d["dictionary"] == "DICT_5X5_100"


def test_marker_observation_model() -> None:
    """Test MarkerObservation corner tracking and dictionary serialization."""
    obs = MarkerObservation(
        marker_id=0,
        corners_2d=((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)),
        frame_path="frame_001.png",
        edge_lengths_2d=[10.0, 10.0, 10.0, 10.0],
    )
    d = obs.to_dict()
    assert d["marker_id"] == 0
    assert len(d["corners_2d"]) == 4
    assert d["frame_path"] == "frame_001.png"
    assert d["edge_lengths_2d"] == [10.0, 10.0, 10.0, 10.0]


def test_reference_measurement_model() -> None:
    """Test ReferenceMeasurement statistics and dictionary serialization."""
    meas = ReferenceMeasurement(
        reconstructed_size=25.0,
        observations=[24.9, 25.0, 25.1],
        mean=25.0,
        median=25.0,
        std_dev=0.08165,
        min_val=24.9,
        max_val=25.1,
        spread=0.2,
        measurement_count=3,
        units="reconstructed_units",
    )
    d = meas.to_dict()
    assert d["reconstructed_size"] == 25.0
    assert d["measurement_count"] == 3
    assert d["spread"] == 0.2


def test_scale_estimate_model() -> None:
    """Test ScaleEstimate fields and dictionary serialization."""
    est = ScaleEstimate(
        known_physical_size_mm=50.0,
        reconstructed_reference_size=25.0,
        scale_factor=2.0,
        variance=0.01,
        confidence=0.95,
        method="ratio",
    )
    d = est.to_dict()
    assert d["known_physical_size_mm"] == 50.0
    assert d["scale_factor"] == 2.0
    assert d["confidence"] == 0.95


def test_scaling_result_model() -> None:
    """Test ScalingResult status, properties, and dictionary serialization."""
    res = ScalingResult(
        input_mesh_path="in.obj",
        output_mesh_path="out.obj",
        status="SUCCESS",
        scale_factor=2.0,
        transformation_origin=(0.0, 0.0, 0.0),
        vertex_count_before=8,
        vertex_count_after=8,
        face_count_before=12,
        face_count_after=12,
    )
    assert res.success is True
    d = res.to_dict()
    assert d["status"] == "SUCCESS"
    assert d["success"] is True
    assert d["scale_factor"] == 2.0
    assert d["vertex_count_before"] == 8
    assert d["vertex_count_after"] == 8
