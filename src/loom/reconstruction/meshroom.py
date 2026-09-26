"""Meshroom / AliceVision photogrammetry engine adapter."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Sequence

from loom.reconstruction.base import ReconstructionEngine
from loom.reconstruction.models import ReconstructionJobConfig, ReconstructionResult


class MeshroomAdapter(ReconstructionEngine):
    """Adapter for Meshroom / AliceVision CLI photogrammetry pipeline."""

    def __init__(self, binary_path: str = "meshroom_batch") -> None:
        self._binary_path = binary_path

    @property
    def backend_name(self) -> str:
        return "meshroom"

    def is_available(self) -> bool:
        """Check if meshroom_batch executable is in PATH or specified location."""
        return shutil.which(self._binary_path) is not None

    def reconstruct(
        self,
        frame_paths: Sequence[Path],
        config: ReconstructionJobConfig,
    ) -> ReconstructionResult:
        """Execute Meshroom reconstruction.

        Raises:
            NotImplementedError: Real Meshroom execution will be implemented in Phase 2.
        """
        raise NotImplementedError(
            "Meshroom backend execution is not yet implemented (scheduled for Phase 2)."
        )
