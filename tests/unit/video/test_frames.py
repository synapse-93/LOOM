"""Unit tests for streaming frame extraction and manifest generation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import cv2
import pytest

from generate_test_video import create_synthetic_test_video
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
    """Verify max_frames caps the extracted frame count and spans across the video."""
    out_dir = tmp_path / "capped_frames"
    config = VideoConfig(sample_interval=1, max_frames=7)
    extractor = FrameExtractor(config=config)

    artifact = extractor.extract(synthetic_video_path, out_dir)

    assert artifact.total_extracted == 7
    assert len(artifact.frame_paths) == 7

    # 30 frames // 7 max_frames = step 4. Samples: 0, 4, 8, 12, 16, 20, 24
    manifest_path = out_dir / "manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["sample_interval"] == 4
    assert manifest["frames"][0]["source_frame_index"] == 0
    assert manifest["frames"][-1]["source_frame_index"] == 24


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


def test_frame_extraction_spans_entire_video_when_capped(tmp_path: Path) -> None:
    """Verify frames span across the full duration when max_frames is smaller than nominal."""
    video_path = tmp_path / "long_synthetic.mp4"
    create_synthetic_test_video(
        output_path=video_path,
        num_frames=60,
        fps=30,
        width=320,
        height=240,
    )

    out_dir = tmp_path / "spanned_frames"
    config = VideoConfig(sample_interval=1, max_frames=6)
    extractor = FrameExtractor(config=config)

    artifact = extractor.extract(video_path, out_dir)

    assert artifact.total_extracted == 6
    assert len(artifact.frame_paths) == 6

    manifest_path = out_dir / "manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # 60 frames // 6 max_frames = step 10 -> frames 0, 10, 20, 30, 40, 50
    assert manifest["sample_interval"] == 10
    extracted_indices = [frame["source_frame_index"] for frame in manifest["frames"]]
    assert extracted_indices == [0, 10, 20, 30, 40, 50]

    # Verify last frame is in the final quartile of the video (spanning coverage)
    assert extracted_indices[-1] >= 45
    # Verify timestamps are strictly monotonically increasing
    timestamps = [frame["timestamp_seconds"] for frame in manifest["frames"]]
    assert timestamps == sorted(timestamps)
    assert len(set(timestamps)) == len(timestamps)


def test_frame_extraction_preserves_target_fps_when_under_max_frames(tmp_path: Path) -> None:
    """Verify target_fps is respected when nominal sample count is under max_frames."""
    video_path = tmp_path / "target_fps_synthetic.mp4"
    create_synthetic_test_video(
        output_path=video_path,
        num_frames=60,
        fps=30,
        width=320,
        height=240,
    )

    out_dir = tmp_path / "target_fps_frames"
    # 30 fps with target_fps 10 -> step 3. 60 // 3 = 20 samples <= 50 max_frames.
    config = VideoConfig(sample_interval=1, target_fps=10.0, max_frames=50)
    extractor = FrameExtractor(config=config)

    artifact = extractor.extract(video_path, out_dir)

    assert artifact.total_extracted == 20
    assert artifact.metadata["sample_step"] == 3


def test_frame_extraction_adjusts_step_when_target_fps_exceeds_max_frames(tmp_path: Path) -> None:
    """Verify step expands when target_fps would produce more than max_frames."""
    video_path = tmp_path / "target_fps_capped_synthetic.mp4"
    create_synthetic_test_video(
        output_path=video_path,
        num_frames=60,
        fps=30,
        width=320,
        height=240,
    )

    out_dir = tmp_path / "target_fps_capped_frames"
    # 30 fps with target_fps 15 -> nominal step 2 -> 30 samples. But max_frames=5!
    # Stride should expand to 60 // 5 = 12.
    config = VideoConfig(sample_interval=1, target_fps=15.0, max_frames=5)
    extractor = FrameExtractor(config=config)

    artifact = extractor.extract(video_path, out_dir)

    assert artifact.total_extracted == 5
    manifest_path = out_dir / "manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest["sample_interval"] == 12
    extracted_indices = [frame["source_frame_index"] for frame in manifest["frames"]]
    assert extracted_indices == [0, 12, 24, 36, 48]


def test_frame_extraction_handles_unknown_frame_count(synthetic_video_path: Path, tmp_path: Path) -> None:
    """Verify extractor falls back safely when cv2.CAP_PROP_FRAME_COUNT returns 0."""
    out_dir = tmp_path / "unknown_cnt_frames"
    config = VideoConfig(sample_interval=2, max_frames=5)
    extractor = FrameExtractor(config=config)

    orig_video_capture = cv2.VideoCapture

    class VideoCaptureWrapper:
        def __init__(self, *args, **kwargs) -> None:
            self._real = orig_video_capture(*args, **kwargs)

        def isOpened(self) -> bool:
            return self._real.isOpened()

        def get(self, prop_id: int) -> float:
            if prop_id == cv2.CAP_PROP_FRAME_COUNT:
                return 0.0
            return float(self._real.get(prop_id))

        def read(self):
            return self._real.read()

        def release(self) -> None:
            self._real.release()

    with patch("cv2.VideoCapture", side_effect=VideoCaptureWrapper):
        artifact = extractor.extract(synthetic_video_path, out_dir)

    assert artifact.total_extracted == 5
    assert artifact.metadata["sample_step"] == 2
