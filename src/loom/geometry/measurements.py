"""3D bounding box and dimensional measurement data models."""

from __future__ import annotations

from dataclasses import dataclass
from loom.geometry.coordinates import Point3D


@dataclass(frozen=True)
class BoundingBox3D:
    """Axis-Aligned Bounding Box (AABB) in 3D Euclidean space."""

    min_point: Point3D
    max_point: Point3D

    def __post_init__(self) -> None:
        if (
            self.min_point.x > self.max_point.x
            or self.min_point.y > self.max_point.y
            or self.min_point.z > self.max_point.z
        ):
            raise ValueError(
                f"Invalid bounding box: min_point {self.min_point} exceeds max_point {self.max_point}"
            )

    @property
    def width(self) -> float:
        """Extent along X axis."""
        return self.max_point.x - self.min_point.x

    @property
    def depth(self) -> float:
        """Extent along Y axis."""
        return self.max_point.y - self.min_point.y

    @property
    def height(self) -> float:
        """Extent along Z axis."""
        return self.max_point.z - self.min_point.z

    @property
    def dimensions(self) -> tuple[float, float, float]:
        """Return (width, depth, height) extents."""
        return (self.width, self.depth, self.height)

    @property
    def volume(self) -> float:
        """Compute volume of the bounding box."""
        return self.width * self.depth * self.height

    @property
    def center(self) -> Point3D:
        """Compute center coordinate of the bounding box."""
        return Point3D(
            (self.min_point.x + self.max_point.x) / 2.0,
            (self.min_point.y + self.max_point.y) / 2.0,
            (self.min_point.z + self.max_point.z) / 2.0,
        )
