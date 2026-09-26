"""Streaming frame extraction interfaces for LOOM."""

from __future__ import annotations

from pathlib import Path
from loom.config.models import VideoConfig
from loom.pipeline.artifacts import FrameSetArtifact


class FrameExtractor:
    """Interface for extracting sequential video frames in a streaming pipeline.

    Contract:
        Frames must be processed in a streaming fashion (generator/sequential decoding)
        to prevent out-of-memory errors on 4K smartphone video files.
    """

    def __init__(self, config: VideoConfig) -> None:
        self.config = config

    def extract(self, video_path: Path, output_dir: Path) -> FrameSetArtifact:
        """Extract frames according to VideoConfig sampling rate.

        Args:
            video_path: Source video path.
            output_dir: Destination directory for extracted image frames.

        Returns:
            FrameSetArtifact containing list of extracted frame paths.

        Raises:
            NotImplementedError: Implementation scheduled for Phase 1.
        """
        raise NotImplementedError("Streaming frame extraction scheduled for Phase 1.")
