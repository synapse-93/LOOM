"""Video metadata extraction interfaces and data models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class VideoMetadata:
    """Metadata describing physical and stream properties of a video."""

    file_path: Path
    duration_seconds: float
    frame_count: int
    fps: float
    width: int
    height: int
    codec: str
    file_size_bytes: int


def extract_video_metadata(video_path: Path) -> VideoMetadata:
    """Extract metadata from video container without loading frames into memory.

    Args:
        video_path: Path to video file.

    Returns:
        VideoMetadata descriptor.

    Raises:
        NotImplementedError: Implementation scheduled for Phase 1.
    """
    raise NotImplementedError("Video metadata extraction scheduled for Phase 1.")
