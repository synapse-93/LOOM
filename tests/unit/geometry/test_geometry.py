"""Tests for 3D geometry primitives, bounding boxes, and coordinate transforms."""

from __future__ import annotations

import math
import pytest
from loom.geometry.coordinates import Point3D, Vector3D
from loom.geometry.measurements import BoundingBox3D
from loom.geometry.transforms import TransformMatrix4x4


def test_point_distance() -> None:
    """Verify 3D Euclidean distance calculation."""
    p1 = Point3D(0.0, 0.0, 0.0)
    p2 = Point3D(3.0, 4.0, 0.0)
    assert p1.distance_to(p2) == 5.0


def test_vector_operations() -> None:
    """Verify vector magnitude, normalization, dot, and cross products."""
    v1 = Vector3D(1.0, 0.0, 0.0)
    v2 = Vector3D(0.0, 1.0, 0.0)
    assert v1.magnitude == 1.0
    assert v1.dot(v2) == 0.0
    cross = v1.cross(v2)
    assert cross == Vector3D(0.0, 0.0, 1.0)


def test_bounding_box_3d() -> None:
    """Verify BoundingBox3D dimensions and volume calculation."""
    bbox = BoundingBox3D(
        min_point=Point3D(0.0, 0.0, 0.0),
        max_point=Point3D(10.0, 20.0, 30.0),
    )
    assert bbox.width == 10.0
    assert bbox.depth == 20.0
    assert bbox.height == 30.0
    assert bbox.volume == 6000.0
    assert bbox.center == Point3D(5.0, 10.0, 15.0)

    # Invalid bounding box raises ValueError
    with pytest.raises(ValueError):
        BoundingBox3D(min_point=Point3D(10.0, 0.0, 0.0), max_point=Point3D(5.0, 0.0, 0.0))


def test_transform_matrix_scale() -> None:
    """Verify uniform scaling transform on 3D point."""
    scale = TransformMatrix4x4.uniform_scale(2.5)
    pt = Point3D(2.0, 4.0, 6.0)
    transformed = scale.transform_point(pt)
    assert transformed == Point3D(5.0, 10.0, 15.0)
