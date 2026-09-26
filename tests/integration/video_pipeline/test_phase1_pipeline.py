"""Integration tests for Phase 1 end-to-end video ingest and capture quality pipeline."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from loom.config.models import LoomConfig, VideoConfig, CaptureConfig
from loom.pipeline.runner import run_phase1_pipeline


def test_phase1_pipeline_end_to_end(synthetic_video_path: Path, tmp_path: Path) -> None:
    """Verify complete Phase 1 pipeline execution on synthetic video.

    Pipeline flow:
    synthetic video
        ↓
    VideoIngestor
        ↓
    metadata extraction
        ↓
    FrameExtractor (streaming)
        ↓
    quality analysis (sharpness, brightness, contrast, blur, redundancy)
        ↓
    selected frames
        ↓
    CaptureAnalysisArtifact
        ↓
    JSON reports + log verification
    """
    output_root = tmp_path / "loom_outputs"
    config = LoomConfig(
        output_dir=output_root,
        video=VideoConfig(sample_interval=1, max_frames=50),
        capture=CaptureConfig(sharpness_threshold=50.0, redundancy_threshold=0.98),
    )

    result = run_phase1_pipeline(synthetic_video_path, config)

    assert result.run_dir.is_dir()
    assert result.metadata_report_path.is_file()
    assert result.capture_report_path.is_file()

    # 1. Output directory layout verification
    raw_frames_dir = result.run_dir / "frames" / "raw"
    selected_frames_dir = result.run_dir / "frames" / "selected"
    reports_dir = result.run_dir / "reports"
    logs_dir = result.run_dir / "logs"

    assert raw_frames_dir.is_dir()
    assert selected_frames_dir.is_dir()
    assert reports_dir.is_dir()
    assert logs_dir.is_dir()

    # 2. Raw and selected frames
    raw_files = list(raw_frames_dir.glob("frame_*.jpg"))
    assert len(raw_files) == 30  # synthetic video has 30 frames
    assert (raw_frames_dir / "manifest.json").is_file()

    selected_files = list(selected_frames_dir.glob("frame_*.jpg"))
    assert len(selected_files) > 0
    assert len(selected_files) <= len(raw_files)
    assert len(result.capture_analysis_artifact.selected_frames) == len(selected_files)

    # 3. Metadata report
    metadata_json_path = reports_dir / "metadata.json"
    assert metadata_json_path.is_file()
    with open(metadata_json_path, "r", encoding="utf-8") as f:
        meta_data = json.load(f)

    assert meta_data["frame_count"] == 30
    assert meta_data["width"] == 320
    assert meta_data["height"] == 240
    assert meta_data["fps"] == 15.0

    # 4. Capture analysis report
    analysis_json_path = reports_dir / "capture_analysis.json"
    assert analysis_json_path.is_file()
    with open(analysis_json_path, "r", encoding="utf-8") as f:
        analysis_data = json.load(f)

    assert "selected_frames" in analysis_data
    assert "rejected_frames" in analysis_data
    assert "average_sharpness" in analysis_data
    assert "guidance_notes" in analysis_data
    assert "metadata" in analysis_data
    assert analysis_data["metadata"]["selected_count"] == len(selected_files)
    assert analysis_data["metadata"]["rejected_count"] == len(raw_files) - len(selected_files)

    # 5. Pipeline log file
    log_file = logs_dir / "pipeline.log"
    assert log_file.is_file()
    assert log_file.stat().st_size > 0


def test_phase1_pipeline_multiple_runs_do_not_collide(synthetic_video_path: Path, tmp_path: Path) -> None:
    """Verify sequential pipeline runs produce distinct run directories without overwriting."""
    output_root = tmp_path / "loom_outputs"
    config = LoomConfig(
        output_dir=output_root,
        video=VideoConfig(sample_interval=2, max_frames=10),
    )

    result1 = run_phase1_pipeline(synthetic_video_path, config)
    # Ensure slightly different timestamp if called quickly
    import time
    time.sleep(1.05)
    result2 = run_phase1_pipeline(synthetic_video_path, config)

    assert result1.run_dir != result2.run_dir
    assert result1.run_dir.is_dir()
    assert result2.run_dir.is_dir()
