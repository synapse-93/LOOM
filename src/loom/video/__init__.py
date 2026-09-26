"""Video processing and frame extraction module for LOOM."""

from __future__ import annotations

from loom.video.frames import FrameExtractor
from loom.video.ingest import VideoIngestor
from loom.video.metadata import VideoMetadata, extract_video_metadata

__all__ = [
    "FrameExtractor",
    "VideoIngestor",
    "VideoMetadata",
    "extract_video_metadata",
]
