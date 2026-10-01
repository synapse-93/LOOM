"""Domain exceptions for 3D mesh processing and geometry repair."""

from __future__ import annotations


class MeshError(Exception):
    """Base exception for all mesh processing failures."""


class MeshLoadError(MeshError):
    """Raised when a 3D mesh file cannot be loaded or parsed."""


class MeshFormatError(MeshError, ValueError):
    """Raised when a mesh file format is unsupported."""


class MeshInvalidError(MeshError, ValueError):
    """Raised when an input mesh lacks usable geometric primitives."""


class MeshProcessingError(MeshError):
    """Raised when an error occurs during mesh cleanup, component filtering, or repair."""
