"""Geometry primitives, measurement utilities, and mesh processing for LOOM."""

from __future__ import annotations

from loom.geometry.alignment import AlignmentResult, CoordinateNormalizer, PlaneModel
from loom.geometry.coordinates import Point3D, Vector3D
from loom.geometry.measurements import BoundingBox3D
from loom.geometry.segmentation import ForegroundSegmenter, SegmentationResult
from loom.geometry.transforms import TransformMatrix4x4
from loom.mesh.diagnostics import MeshDiagnostics
from loom.mesh.models import GeometryDiagnostics, MeshProcessingResult
from loom.mesh.processor import MeshProcessor

__all__ = [
    "AlignmentResult",
    "BoundingBox3D",
    "CoordinateNormalizer",
    "ForegroundSegmenter",
    "GeometryDiagnostics",
    "MeshDiagnostics",
    "MeshProcessingResult",
    "MeshProcessor",
    "PlaneModel",
    "Point3D",
    "SegmentationResult",
    "TransformMatrix4x4",
    "Vector3D",
]
