"""Integration test verifying end-to-end scaffold dry-run."""

from __future__ import annotations

from pathlib import Path
from loom.config.models import LoomConfig
from loom.pipeline.artifacts import VideoArtifact
from loom.pipeline.runner import PipelineRunner
from loom.pipeline.stages import PipelineStage


class MockIngestStage(PipelineStage[VideoArtifact, VideoArtifact]):
    def execute(self, input_artifact: VideoArtifact, config: LoomConfig) -> VideoArtifact:
        return input_artifact


def test_full_pipeline_scaffold_dry_run() -> None:
    """Verify that pipeline runner can assemble stages and validate preconditions."""
    config = LoomConfig()
    runner = PipelineRunner(config)

    stage = MockIngestStage(name="video_ingest_check")
    runner.register_stage(stage)

    video_art = VideoArtifact(
        stage_name="input",
        video_path=Path("sample.mp4"),
        duration_seconds=10.0,
        frame_count=300,
        resolution=(1920, 1080),
        fps=30.0,
    )

    status = runner.dry_run(video_art)
    assert status["video_ingest_check"] is True
