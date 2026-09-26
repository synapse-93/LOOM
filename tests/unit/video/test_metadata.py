"""Unit tests for video container metadata extraction."""

from __future__ import annotations

from pathlib import Path
import pytest
from loom.video.metadata import extract_video_metadata, VideoMetadata


def test_extract_metadata_success(synthetic_video_path: Path) -> None:
    """Verify metadata extraction correctly reads stream properties from a valid video."""
    meta = extract_video_metadata(synthetic_video_path)

    assert isinstance(meta, VideoMetadata)
    assert meta.file_path == synthetic_video_path.resolve()
    assert meta.file_size_bytes > 0
    assert meta.frame_count == 30
    assert meta.fps == 15.0
    assert meta.width == 320
    assert meta.height == 240
    assert meta.duration_seconds == pytest.approx(2.0, rel=0.1)
    assert meta.codec is not None
    assert len(meta.codec) > 0


def test_extract_metadata_nonexistent_file(tmp_path: Path) -> None:
    """Verify non-existent video file raises FileNotFoundError."""
    missing = tmp_path / "does_not_exist.mp4"
    with pytest.raises(FileNotFoundError, match="Video file not found"):
        extract_video_metadata(missing)


def test_extract_metadata_empty_file(tmp_path: Path) -> None:
    """Verify zero-byte video file raises ValueError."""
    empty = tmp_path / "empty_video.mp4"
    empty.write_bytes(b"")
    with pytest.raises(ValueError, match="empty"):
        extract_video_metadata(empty)


def test_extract_metadata_corrupt_file(tmp_path: Path) -> None:
    """Verify unreadable video stream raises ValueError with actionable message."""
    corrupt = tmp_path / "corrupt_data.mp4"
    corrupt.write_bytes(b"This is not a real video stream.")
    with pytest.raises(ValueError, match="OpenCV could not initialize a readable video stream"):
        extract_video_metadata(corrupt)
