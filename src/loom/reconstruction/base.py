"""Abstract interface for external 3D reconstruction engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Sequence

from loom.reconstruction.models import ReconstructionJobConfig, ReconstructionResult


class ReconstructionEngine(ABC):
    """Abstract interface defining the contract for photogrammetry backends.

    Design Principle:
        The rest of the LOOM pipeline must interact exclusively through this interface.
        Never import Meshroom or COLMAP adapter logic directly into mesh, scaling, or export modules.
    """

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Name of the reconstruction engine backend."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if required external binaries are present on the host system."""
        ...

    @abstractmethod
    def reconstruct(
        self,
        frame_paths: Sequence[Path],
        config: ReconstructionJobConfig,
    ) -> ReconstructionResult:
        """Execute 3D reconstruction pipeline on input keyframes.

        Args:
            frame_paths: Sequence of keyframe image paths.
            config: Job configuration settings.

        Returns:
            ReconstructionResult with paths to generated mesh and logs.

        Raises:
            NotImplementedError: For scaffolded backends not yet implemented.
            RuntimeError: If execution fails or external binary crashes.
        """
        ...
