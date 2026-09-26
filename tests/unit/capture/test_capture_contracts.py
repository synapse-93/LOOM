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


def test_frame_quality_assessor_raises_not_implemented() -> None:
    """Verify FrameQualityAssessor raises NotImplementedError on scaffolded methods."""
    assessor = FrameQualityAssessor(config=CaptureConfig())
    with pytest.raises(NotImplementedError):
        assessor.compute_sharpness(Path("frame.png"))

    with pytest.raises(NotImplementedError):
        assessor.filter_keyframes([Path("frame1.png"), Path("frame2.png")])


def test_coverage_estimator_raises_not_implemented() -> None:
    """Verify CoverageEstimator raises NotImplementedError on scaffolded methods."""
    estimator = CoverageEstimator()
    with pytest.raises(NotImplementedError):
        estimator.estimate_coverage([Path("frame1.png")])
