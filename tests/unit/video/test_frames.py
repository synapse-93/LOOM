"""Unit tests for streaming frame extraction and manifest generation."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from loom.config.models import VideoConfig
from loom.video.frames import FrameExtractor


def test_frame_extraction_all_frames(synthetic_video_path: Path, tmp_path: Path) -> None:
    """Verify streaming extractor extracts all frames when sample_interval=1."""
    out_dir = tmp_path / "extracted_frames"
    config = VideoConfig(sample_interval=1, max_frames=100)
    extractor = FrameExtractor(config=config)

    artifact = extractor.extract(synthetic_video_path, out_dir)

    assert artifact.total_extracted == 30
    assert len(artifact.frame_paths) == 30
    assert artifact.frames_dir == out_dir.resolve()
    for p in artifact.frame_paths:
        assert p.is_file()
        assert p.suffix.lower() == ".jpg"


def test_frame_extraction_sampling_interval(synthetic_video_path: Path, tmp_path: Path) -> None:
    """Verify sample_interval skips frames accurately."""
    out_dir = tmp_path / "sampled_frames"
    config = VideoConfig(sample_interval=2, max_frames=100)
    extractor = FrameExtractor(config=config)

    artifact = extractor.extract(synthetic_video_path, out_dir)

    # 30 frames sampled every 2 -> 15 frames
    assert artifact.total_extracted == 15
    assert len(artifact.frame_paths) == 15


def test_frame_extraction_max_frames_limit(synthetic_video_path: Path, tmp_path: Path) -> None:
    """Verify max_frames caps the extracted frame count."""
    out_dir = tmp_path / "capped_frames"
    config = VideoConfig(sample_interval=1, max_frames=7)
    extractor = FrameExtractor(config=config)

    artifact = extractor.extract(synthetic_video_path, out_dir)

    assert artifact.total_extracted == 7
    assert len(artifact.frame_paths) == 7


def test_frame_manifest_and_timestamps(synthetic_video_path: Path, tmp_path: Path) -> None:
    """Verify manifest.json is generated with deterministic names, frame indices, and timestamps."""
    out_dir = tmp_path / "manifest_frames"
    config = VideoConfig(sample_interval=3, max_frames=100)
    extractor = FrameExtractor(config=config)

    artifact = extractor.extract(synthetic_video_path, out_dir)

    manifest_path = out_dir / "manifest.json"
    assert manifest_path.is_file()

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest["source_frame_count"] == 30
    assert manifest["fps"] == 15.0
    assert manifest["total_extracted"] == artifact.total_extracted
    assert len(manifest["frames"]) == artifact.total_extracted

    # Check frame entries
    frames = manifest["frames"]
    for i, entry in enumerate(frames):
        expected_idx = i * 3
        assert entry["source_frame_index"] == expected_idx
        expected_time = expected_idx / 15.0
        assert entry["timestamp_seconds"] == pytest.approx(expected_time, rel=1e-2)
        assert entry["filename"] == f"frame_{expected_idx:06d}.jpg"
        assert (out_dir / entry["filename"]).is_file()
