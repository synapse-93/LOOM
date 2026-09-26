"""Tests for capture quality and guidance interfaces."""

from __future__ import annotations

from pathlib import Path
import pytest
from loom.capture.coverage import CoverageEstimator
from loom.capture.guidance import CaptureGuidance
from loom.capture.quality import FrameQualityAssessor
from loom.config.models import CaptureConfig


def test_capture_guidance_generation() -> None:
    """Verify CaptureGuidance provides actionable feedback based on metrics."""
    notes = CaptureGuidance.generate_recommendations(
        average_sharpness=50.0,
        blur_ratio=0.5,
        coverage_score=0.4,
    )
    assert len(notes) == 2
    assert any("motion blur" in n.lower() for n in notes)
    assert any("orbit" in n.lower() or "coverage" in n.lower() for n in notes)


def test_frame_quality_assessor_missing_file_raises() -> None:
    """Verify FrameQualityAssessor raises ValueError when given non-existent frame paths."""
    assessor = FrameQualityAssessor(config=CaptureConfig())
    with pytest.raises(ValueError, match="Unable to read frame"):
        assessor.compute_sharpness(Path("non_existent_frame.png"))

    with pytest.raises(ValueError, match="Failed to load image|Unable to read frame"):
        assessor.evaluate_frame(Path("non_existent_frame.png"))


def test_coverage_estimator_interface(tmp_path: Path) -> None:
    """Verify CoverageEstimator calculates 2D frame diversity score."""
    import cv2
    import numpy as np

    # Create 2 small test frames
    f1 = tmp_path / "f1.jpg"
    f2 = tmp_path / "f2.jpg"
    img1 = np.full((64, 64, 3), 100, dtype=np.uint8)
    img2 = np.full((64, 64, 3), 200, dtype=np.uint8)
    cv2.imwrite(str(f1), img1)
    cv2.imwrite(str(f2), img2)

    estimator = CoverageEstimator()
    score = estimator.estimate_coverage([f1, f2])
    assert 0.0 <= score <= 1.0
