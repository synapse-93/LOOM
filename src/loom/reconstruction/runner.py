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
    def get_engine(cls, backend_name: str = "meshroom") -> ReconstructionEngine:
        """Instantiate requested reconstruction engine adapter.

        Args:
            backend_name: Name of backend ('meshroom' or 'colmap').

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
        return engine_cls()
