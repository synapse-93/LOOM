"""Exceptions for 3D photogrammetric reconstruction subsystem."""

from __future__ import annotations


class ReconstructionError(Exception):
    """Base exception for 3D reconstruction failures."""


class ReconstructionBinaryNotFoundError(ReconstructionError):
    """Raised when external photogrammetry engine executable is not found."""


class ReconstructionInvalidInputError(ReconstructionError, ValueError, FileNotFoundError):
    """Raised when input frame sequence is empty, missing, or in an unsupported format."""


class ReconstructionExecutionError(ReconstructionError):
    """Raised when external photogrammetry subprocess exits with non-zero status."""


class ReconstructionTimeoutError(ReconstructionExecutionError):
    """Raised when external photogrammetry execution exceeds configured timeout limit."""


class ReconstructionArtifactNotFoundError(ReconstructionError):
    """Raised when expected 3D mesh or output artifacts are missing after execution."""


class ReconstructionPartialError(ReconstructionError):
    """Raised when reconstruction produced partial artifacts (e.g. camera poses or point clouds) but mesh generation failed."""
