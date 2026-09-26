"""Tests for video module interfaces and contracts."""

from __future__ import annotations

from pathlib import Path
import pytest
from loom.config.models import VideoConfig
from loom.video.frames import FrameExtractor
from loom.video.ingest import VideoIngestor
from loom.video.metadata import extract_video_metadata


def test_video_file_validation(tmp_path: Path) -> None:
    """Verify VideoIngestor validates extensions and file existence."""
    # Non-existent file
    with pytest.raises(FileNotFoundError):
        VideoIngestor.validate_video_file(tmp_path / "missing.mp4")

    # Empty file
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    with pytest.raises(ValueError, match="empty"):
        VideoIngestor.validate_video_file(empty)

    # Unsupported extension
    unsupported = tmp_path / "file.txt"
    unsupported.write_bytes(b"data")
    with pytest.raises(ValueError, match="Unsupported video format"):
        VideoIngestor.validate_video_file(unsupported)

    # Valid container format
    valid = tmp_path / "valid.mp4"
    valid.write_bytes(b"dummy_video_bytes")
    assert VideoIngestor.validate_video_file(valid) is True


def test_frame_extractor_missing_file_raises(tmp_path: Path) -> None:
    """Verify FrameExtractor raises FileNotFoundError when source video does not exist."""
    extractor = FrameExtractor(config=VideoConfig())
    with pytest.raises(FileNotFoundError, match="Source video not found"):
        extractor.extract(tmp_path / "missing.mp4", tmp_path / "outputs")


def test_extract_video_metadata_errors(tmp_path: Path) -> None:
    """Verify extract_video_metadata raises expected errors for missing/corrupt files."""
    # Missing file
    with pytest.raises(FileNotFoundError, match="Video file not found"):
        extract_video_metadata(tmp_path / "missing.mp4")

    # Empty file
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    with pytest.raises(ValueError, match="empty"):
        extract_video_metadata(empty)

    # Corrupt/non-video file
    corrupt = tmp_path / "corrupt.mp4"
    corrupt.write_bytes(b"not a valid video container content at all")
    with pytest.raises(ValueError, match="OpenCV could not initialize a readable video stream"):
        extract_video_metadata(corrupt)
