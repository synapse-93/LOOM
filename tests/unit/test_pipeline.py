"""Tests for pipeline stage contracts and runner dry-run orchestration."""

from __future__ import annotations

import pytest
from loom.config.models import LoomConfig
from loom.pipeline.artifacts import BaseArtifact
from loom.pipeline.runner import PipelineRunner
from loom.pipeline.stages import PipelineStage


class MockScaffoldStage(PipelineStage[BaseArtifact, BaseArtifact]):
    """Sample stage testing stage interface contract."""

    def execute(self, input_artifact: BaseArtifact, config: LoomConfig) -> BaseArtifact:
        raise NotImplementedError("Scaffold stage not implemented.")

    def dry_run(self, input_artifact: BaseArtifact, config: LoomConfig) -> bool:
        return input_artifact is not None


def test_pipeline_runner_registration_and_dry_run() -> None:
    """Verify PipelineRunner registers stages and executes dry-run validation."""
    config = LoomConfig()
    runner = PipelineRunner(config)

    stage_a = MockScaffoldStage(name="stage_a")
    stage_b = MockScaffoldStage(name="stage_b")
    runner.register_stage(stage_a)
    runner.register_stage(stage_b)

    assert len(runner.stages) == 2

    initial_art = BaseArtifact(stage_name="init")
    dry_run_results = runner.dry_run(initial_art)

    assert dry_run_results["stage_a"] is True
    assert dry_run_results["stage_b"] is True


def test_pipeline_runner_raises_not_implemented() -> None:
    """Verify execution of scaffolded stage raises NotImplementedError cleanly."""
    config = LoomConfig()
    runner = PipelineRunner(config)
    runner.register_stage(MockScaffoldStage(name="unimplemented_stage"))

    initial_art = BaseArtifact(stage_name="init")
    with pytest.raises(NotImplementedError):
        runner.run(initial_art)
