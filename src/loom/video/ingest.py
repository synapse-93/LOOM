"""Video ingestion and validation for LOOM."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from loom.pipeline.artifacts import VideoArtifact
from loom.video.metadata import VideoMetadata, extract_video_metadata

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}


class VideoIngestor:
    """Validates and ingests consumer smartphone video captures."""

    @staticmethod
    def validate_video_file(video_path: Path) -> bool:
        """Verify video exists, has supported container format, and is non-empty.

        Args:
            video_path: Path to video file.

        Returns:
            True if file is valid.

        Raises:
            FileNotFoundError: If path does not exist.
            ValueError: If file is empty or has unsupported extension.
        """
        p = Path(video_path).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"Video file not found: {p}")
        if p.stat().st_size == 0:
            raise ValueError(f"Video file is empty (0 bytes): {p}")

        if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported video format '{p.suffix}'. Expected one of {sorted(SUPPORTED_EXTENSIONS)}"
            )
        return True

    def ingest(
        self,
        video_path: Path,
        min_width: int = 0,
        min_height: int = 0,
    ) -> VideoArtifact:
        """Ingest source video, extract metadata, and produce validated VideoArtifact.

        Args:
            video_path: Path to input video file.
            min_width: Optional minimum width constraint.
            min_height: Optional minimum height constraint.

        Returns:
            Validated VideoArtifact ready for downstream frame extraction.

        Raises:
            FileNotFoundError: If video does not exist.
            ValueError: If video is invalid or fails resolution thresholds.
        """
        self.validate_video_file(video_path)
        metadata: VideoMetadata = extract_video_metadata(video_path)

        if min_width > 0 and metadata.width < min_width:
            raise ValueError(
                f"Video width {metadata.width}px is below minimum requirement of {min_width}px."
            )
        if min_height > 0 and metadata.height < min_height:
            raise ValueError(
                f"Video height {metadata.height}px is below minimum requirement of {min_height}px."
            )

        logger.info(
            "Ingested video '%s': %dx%d @ %.2f fps, %d frames (%.2fs)",
            metadata.file_path.name,
            metadata.width,
            metadata.height,
            metadata.fps,
            metadata.frame_count,
            metadata.duration_seconds,
        )

        return VideoArtifact(
            stage_name="video_ingest",
            video_path=metadata.file_path,
            duration_seconds=metadata.duration_seconds,
            frame_count=metadata.frame_count,
            resolution=(metadata.width, metadata.height),
            fps=metadata.fps,
            metadata={
                "codec": metadata.codec,
                "file_size_bytes": metadata.file_size_bytes,
            },
        )
