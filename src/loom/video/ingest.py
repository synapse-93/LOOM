"""Video ingestion and validation interfaces."""

from __future__ import annotations

from pathlib import Path
from loom.pipeline.artifacts import VideoArtifact


class VideoIngestor:
    """Interface for verifying and ingesting smartphone video captures."""

    @staticmethod
    def validate_video_file(video_path: Path) -> bool:
        """Verify video exists, has supported container format, and is non-empty.

        Args:
            video_path: Path to video file.

        Returns:
            True if file is valid.

        Raises:
            FileNotFoundError: If path does not exist.
            ValueError: If file is not a valid video format.
        """
        p = Path(video_path).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"Video file not found: {p}")
        if p.stat().st_size == 0:
            raise ValueError(f"Video file is empty: {p}")
        supported_extensions = {".mp4", ".mov", ".m4v", ".avi"}
        if p.suffix.lower() not in supported_extensions:
            raise ValueError(
                f"Unsupported video format '{p.suffix}'. Expected one of {supported_extensions}"
            )
        return True

    def ingest(self, video_path: Path) -> VideoArtifact:
        """Ingest video and produce VideoArtifact.

        Raises:
            NotImplementedError: Scheduled for Phase 1.
        """
        raise NotImplementedError("Video ingestion scheduled for Phase 1.")
