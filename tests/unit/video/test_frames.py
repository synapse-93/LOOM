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


def test_compute_laplacian_variance() -> None:
    """Verify Laplacian variance correctly differentiates sharp from blurry images."""
    import numpy as np
    import cv2
    from loom.video.frames import compute_laplacian_variance

    # Sharp checkerboard pattern
    sharp_img = np.zeros((100, 100, 3), dtype=np.uint8)
    sharp_img[::20, :] = 255
    sharp_img[:, ::20] = 255
    sharp_score = compute_laplacian_variance(sharp_img)

    # Heavily blurred version
    blurred_img = cv2.GaussianBlur(sharp_img, (25, 25), 10.0)
    blurred_score = compute_laplacian_variance(blurred_img)

    assert sharp_score > 100.0
    assert blurred_score < 25.0
    assert sharp_score > blurred_score * 10


def test_frame_extraction_blur_rejection_and_fallback(synthetic_video_path: Path, tmp_path: Path) -> None:
    """Verify FrameExtractor rejects blurred candidate frames and falls back to sharp adjacent frames."""
    from loom.video.frames import compute_laplacian_variance

    out_dir = tmp_path / "blur_rejection_frames"
    # synthetic_video_path has frames 20..29 heavily blurred (< 5.0 variance) and 0..19 sharp (> 800 variance)
    config = VideoConfig(sample_interval=1, max_frames=30, blur_threshold=50.0)
    extractor = FrameExtractor(config=config)

    artifact = extractor.extract(synthetic_video_path, out_dir)

    assert artifact.total_extracted == 30

    manifest_path = out_dir / "manifest.json"
    assert manifest_path.is_file()
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # Check that blurry candidate frames (20..24) within search radius fall back to sharp frame 19
    frames = manifest["frames"]
    for entry in frames:
        c_idx = entry["source_frame_index"]
        res_idx = entry["resolved_frame_index"]
        sharpness = entry["sharpness"]
        if 20 <= c_idx <= 24:
            assert res_idx == 19
            assert sharpness >= 50.0


def test_frame_extraction_even_striding(synthetic_video_path: Path, tmp_path: Path) -> None:
    """Verify even striding across video duration when source_frame_count exceeds max_frames."""
    out_dir = tmp_path / "strided_frames"
    # synthetic_video_path has 30 frames. Request max_frames=5 with sample_interval=1
    config = VideoConfig(sample_interval=1, max_frames=5)
    extractor = FrameExtractor(config=config)

    artifact = extractor.extract(synthetic_video_path, out_dir)

    assert artifact.total_extracted == 5

    manifest_path = out_dir / "manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    extracted_indices = [entry["source_frame_index"] for entry in manifest["frames"]]
    # Should be evenly spaced across 0..29: [0, 7, 14, 22, 29]
    assert extracted_indices[0] == 0
    assert extracted_indices[-1] == 29
    assert len(extracted_indices) == 5
    # Strides between consecutive samples should be roughly equal (approx 7)
    diffs = [extracted_indices[i+1] - extracted_indices[i] for i in range(len(extracted_indices)-1)]
    for d in diffs:
        assert 6 <= d <= 8

