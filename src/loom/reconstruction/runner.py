"""Reconstruction engine coordinator and factory."""

from __future__ import annotations

import logging
from typing import Optional

from loom.reconstruction.base import ReconstructionEngine
from loom.reconstruction.colmap import ColmapAdapter
from loom.reconstruction.meshroom import MeshroomAdapter

logger = logging.getLogger(__name__)


class ReconstructionRunner:
    """Coordinates selection and invocation of ReconstructionEngine backends."""

    _BACKENDS: dict[str, type[ReconstructionEngine]] = {
        "meshroom": MeshroomAdapter,
        "colmap": ColmapAdapter,
    }

    @classmethod
    def get_engine(
        cls,
        backend_name: str = "meshroom",
        binary_path: str | Path | None = None,
    ) -> ReconstructionEngine:
        """Instantiate requested reconstruction engine adapter.

        Args:
            backend_name: Name of backend ('meshroom' or 'colmap').
            binary_path: Optional path to backend executable binary.

        Returns:
            Configured ReconstructionEngine instance.

        Raises:
            ValueError: If requested backend is unknown.
        """
        backend_lower = backend_name.lower()
        engine_cls = cls._BACKENDS.get(backend_lower)
        if engine_cls is None:
            raise ValueError(
                f"Unknown reconstruction backend '{backend_name}'. "
                f"Supported: {list(cls._BACKENDS.keys())}"
            )

        if binary_path is not None:
            return engine_cls(binary_path=binary_path)
        return engine_cls()

    @classmethod
    def run_job(
        cls,
        frame_paths: Sequence[Path],
        config: ReconstructionJobConfig,
        backend_name: str = "meshroom",
    ) -> ReconstructionResult:
        """Instantiate backend engine and execute reconstruction job.

        Args:
            frame_paths: Sequence of keyframe image paths.
            config: Job configuration settings.
            backend_name: Target engine name.

        Returns:
            ReconstructionResult with paths to artifacts and execution status.
        """
        engine = cls.get_engine(backend_name=backend_name, binary_path=config.binary_path)
        return engine.reconstruct(frame_paths, config)
