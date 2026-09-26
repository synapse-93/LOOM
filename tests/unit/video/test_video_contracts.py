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


def test_frame_extractor_scaffold_raises_not_implemented() -> None:
    """Verify FrameExtractor extract method raises NotImplementedError for scaffold."""
    extractor = FrameExtractor(config=VideoConfig())
    with pytest.raises(NotImplementedError):
        extractor.extract(Path("dummy.mp4"), Path("outputs/frames"))


def test_extract_video_metadata_raises_not_implemented() -> None:
    """Verify extract_video_metadata raises NotImplementedError for scaffold."""
    with pytest.raises(NotImplementedError):
        extract_video_metadata(Path("dummy.mp4"))
