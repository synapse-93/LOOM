"""COLMAP Structure-from-Motion and Multi-View Stereo adapter."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Sequence

from loom.reconstruction.base import ReconstructionEngine
from loom.reconstruction.models import ReconstructionJobConfig, ReconstructionResult


class ColmapAdapter(ReconstructionEngine):
    """Adapter for COLMAP CLI photogrammetry pipeline."""

    def __init__(self, binary_path: str = "colmap") -> None:
        self._binary_path = binary_path

    @property
    def backend_name(self) -> str:
        return "colmap"

    def is_available(self) -> bool:
        """Check if colmap executable is present."""
        return shutil.which(self._binary_path) is not None

    def reconstruct(
        self,
        frame_paths: Sequence[Path],
        config: ReconstructionJobConfig,
    ) -> ReconstructionResult:
        """Execute COLMAP reconstruction.

        Raises:
            NotImplementedError: Real COLMAP execution will be implemented in subsequent phases.
        """
        raise NotImplementedError(
            "COLMAP backend execution is not yet implemented (scheduled for subsequent phases)."
        )
