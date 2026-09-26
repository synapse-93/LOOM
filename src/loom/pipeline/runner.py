"""Pipeline runner orchestrating staged execution of VIDEO2PRINT."""

from __future__ import annotations

import logging
from typing import Any, Sequence

from loom.config.models import LoomConfig
from loom.pipeline.artifacts import BaseArtifact
from loom.pipeline.stages import PipelineStage

logger = logging.getLogger(__name__)


class PipelineRunner:
    """Orchestrator for running staged pipeline sequences."""

    def __init__(self, config: LoomConfig) -> None:
        self.config = config
        self._stages: list[PipelineStage[Any, Any]] = []

    def register_stage(self, stage: PipelineStage[Any, Any]) -> None:
        """Register a pipeline stage in sequential order."""
        self._stages.append(stage)

    @property
    def stages(self) -> Sequence[PipelineStage[Any, Any]]:
        """Return registered stages."""
        return tuple(self._stages)

    def dry_run(self, initial_artifact: BaseArtifact) -> dict[str, bool]:
        """Validate preconditions across all registered stages without executing compute.

        Returns:
            Dictionary mapping stage name to boolean readiness status.
        """
        results: dict[str, bool] = {}
        current_artifact: Any = initial_artifact
        for stage in self._stages:
            logger.info("Dry-run checking stage: %s", stage.name)
            is_ready = stage.dry_run(current_artifact, self.config)
            results[stage.name] = is_ready
        return results

    def run(self, initial_artifact: BaseArtifact) -> BaseArtifact:
        """Execute all registered pipeline stages sequentially.

        Raises:
            NotImplementedError: For scaffolded stages that have not been implemented yet.
        """
        current_artifact: Any = initial_artifact
        for stage in self._stages:
            logger.info("Executing stage: %s", stage.name)
            current_artifact = stage.execute(current_artifact, self.config)
        return current_artifact
