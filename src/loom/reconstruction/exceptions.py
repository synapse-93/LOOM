"""Exceptions for 3D photogrammetric reconstruction subsystem."""

from __future__ import annotations


class ReconstructionError(Exception):
    """Base exception for 3D reconstruction failures."""


class ReconstructionBinaryNotFoundError(ReconstructionError):
    """Raised when external photogrammetry engine executable is not found."""


class ReconstructionExecutionError(ReconstructionError):
    """Raised when external photogrammetry subprocess exits with non-zero status."""


class ReconstructionArtifactNotFoundError(ReconstructionError):
    """Raised when expected 3D mesh or output artifacts are missing after execution."""
