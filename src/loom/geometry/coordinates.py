"""Coordinate primitives and 3D Euclidean vector utilities."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Point3D:
    """Represents an immutable 3D Cartesian point."""

    x: float
    y: float
    z: float

    def distance_to(self, other: Point3D) -> float:
        """Euclidean distance to another point."""
        return math.sqrt(
            (self.x - other.x) ** 2 + (self.y - other.y) ** 2 + (self.z - other.z) ** 2
        )

    def as_tuple(self) -> tuple[float, float, float]:
        """Return as coordinate tuple."""
        return (self.x, self.y, self.z)


@dataclass(frozen=True)
class Vector3D:
    """Represents a 3D Euclidean vector."""

    x: float
    y: float
    z: float

    @property
    def magnitude(self) -> float:
        """Compute L2 Euclidean norm."""
        return math.sqrt(self.x**2 + self.y**2 + self.z**2)

    def normalized(self) -> Vector3D:
        """Return unit vector. Raises ZeroDivisionError if magnitude is 0."""
        mag = self.magnitude
        if mag == 0.0:
            raise ZeroDivisionError("Cannot normalize zero-magnitude vector.")
        return Vector3D(self.x / mag, self.y / mag, self.z / mag)

    def dot(self, other: Vector3D) -> float:
        """Dot product with another vector."""
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: Vector3D) -> Vector3D:
        """Cross product with another vector."""
        return Vector3D(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )
