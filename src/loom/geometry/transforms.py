"""4x4 Transformation matrix representation and coordinate transforms."""

from __future__ import annotations

from dataclasses import dataclass
from loom.geometry.coordinates import Point3D, Vector3D


@dataclass(frozen=True)
class TransformMatrix4x4:
    """Homogeneous 4x4 coordinate transformation matrix."""

    matrix: tuple[
        tuple[float, float, float, float],
        tuple[float, float, float, float],
        tuple[float, float, float, float],
        tuple[float, float, float, float],
    ]

    @classmethod
    def identity(cls) -> TransformMatrix4x4:
        """Create identity transform matrix."""
        return cls(
            matrix=(
                (1.0, 0.0, 0.0, 0.0),
                (0.0, 1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            )
        )

    @classmethod
    def uniform_scale(cls, scale_factor: float) -> TransformMatrix4x4:
        """Create uniform scaling matrix."""
        if scale_factor <= 0.0:
            raise ValueError(f"Scale factor must be positive, got {scale_factor}")
        return cls(
            matrix=(
                (scale_factor, 0.0, 0.0, 0.0),
                (0.0, scale_factor, 0.0, 0.0),
                (0.0, 0.0, scale_factor, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            )
        )

    @classmethod
    def translation(cls, dx: float, dy: float, dz: float) -> TransformMatrix4x4:
        """Create translation matrix."""
        return cls(
            matrix=(
                (1.0, 0.0, 0.0, dx),
                (0.0, 1.0, 0.0, dy),
                (0.0, 0.0, 1.0, dz),
                (0.0, 0.0, 0.0, 1.0),
            )
        )

    def transform_point(self, point: Point3D) -> Point3D:
        """Apply transformation matrix to a 3D point."""
        m = self.matrix
        w = m[3][0] * point.x + m[3][1] * point.y + m[3][2] * point.z + m[3][3]
        if w == 0.0:
            raise ZeroDivisionError("Homogeneous coordinate w is zero after transformation.")
        new_x = (m[0][0] * point.x + m[0][1] * point.y + m[0][2] * point.z + m[0][3]) / w
        new_y = (m[1][0] * point.x + m[1][1] * point.y + m[1][2] * point.z + m[1][3]) / w
        new_z = (m[2][0] * point.x + m[2][1] * point.y + m[2][2] * point.z + m[2][3]) / w
        return Point3D(new_x, new_y, new_z)
