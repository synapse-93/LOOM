"""Abstract interface and contracts for LOOM pipeline stages."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from loom.config.models import LoomConfig
from loom.pipeline.artifacts import BaseArtifact

InputArtifactT = TypeVar("InputArtifactT", bound=BaseArtifact)
OutputArtifactT = TypeVar("OutputArtifactT", bound=BaseArtifact)


class PipelineStage(ABC, Generic[InputArtifactT, OutputArtifactT]):
    """Abstract base contract for a discrete, testable pipeline stage."""

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def execute(self, input_artifact: InputArtifactT, config: LoomConfig) -> OutputArtifactT:
        """Execute stage processing logic on input artifact.

        Args:
            input_artifact: Artifact produced by preceding stage.
            config: Complete pipeline configuration.

        Returns:
            OutputArtifact produced by this stage.

        Raises:
            NotImplementedError: If the stage is scaffolded but not yet implemented.
            RuntimeError: If execution fails.
        """
        ...

    def dry_run(self, input_artifact: InputArtifactT, config: LoomConfig) -> bool:
        """Verify preconditions and artifact validity without executing compute.

        Args:
            input_artifact: Input artifact to inspect.
            config: Pipeline configuration.

        Returns:
            True if preconditions are satisfied, False otherwise.
        """
        return input_artifact is not None
