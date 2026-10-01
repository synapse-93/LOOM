"""Geometry primitives, measurement utilities, and mesh processing for LOOM."""

from __future__ import annotations

from loom.geometry.coordinates import Point3D, Vector3D
from loom.geometry.measurements import BoundingBox3D
from loom.geometry.transforms import TransformMatrix4x4
from loom.mesh.diagnostics import MeshDiagnostics
from loom.mesh.models import GeometryDiagnostics, MeshProcessingResult
from loom.mesh.processor import MeshProcessor

__all__ = [
    "BoundingBox3D",
    "GeometryDiagnostics",
    "MeshDiagnostics",
    "MeshProcessingResult",
    "MeshProcessor",
    "Point3D",
    "TransformMatrix4x4",
    "Vector3D",
]
