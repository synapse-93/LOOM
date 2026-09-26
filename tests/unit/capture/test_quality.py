"""Unit tests for optical quality analysis, blur/exposure rejection, and redundancy filtering."""

from __future__ import annotations

from pathlib import Path
import cv2
import numpy as np
import pytest
from loom.capture.quality import FrameQualityAssessor, FrameQualityResult
from loom.config.models import CaptureConfig


def _create_test_frame(
    path: Path,
    brightness: int = 128,
    contrast_scale: float = 1.0,
    add_edges: bool = True,
    blur_ksize: int = 0,
    offset: int = 0,
) -> Path:
    """Helper to create deterministic test image files."""
    img = np.full((120, 160, 3), brightness, dtype=np.uint8)

    if add_edges:
        # Add high-contrast sharp grid lines
        for x in range(offset, 160, 20):
            cv2.line(img, (x, 0), (x, 120), (0, 0, 0), 2)
        for y in range(offset, 120, 20):
            cv2.line(img, (0, y), (160, y), (255, 255, 255), 2)

    if contrast_scale != 1.0:
        img = np.clip(128 + (img.astype(float) - 128) * contrast_scale, 0, 255).astype(np.uint8)

    if blur_ksize > 1:
        if blur_ksize % 2 == 0:
            blur_ksize += 1
        img = cv2.GaussianBlur(img, (blur_ksize, blur_ksize), 0)

    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img)
    return path


def test_sharpness_calculation(tmp_path: Path) -> None:
    """Verify sharp image has substantially higher Laplacian variance than blurred image."""
    sharp_path = _create_test_frame(tmp_path / "sharp.jpg", add_edges=True)
    blurry_path = _create_test_frame(tmp_path / "blurry.jpg", add_edges=True, blur_ksize=21)

    assessor = FrameQualityAssessor(CaptureConfig(sharpness_threshold=50.0))
    sharp_val = assessor.compute_sharpness(sharp_path)
    blurry_val = assessor.compute_sharpness(blurry_path)

    assert sharp_val > blurry_val
    assert sharp_val > 50.0
    assert blurry_val < 50.0


def test_brightness_calculation(tmp_path: Path) -> None:
    """Verify brightness measurement tracks grayscale mean."""
    dark_path = _create_test_frame(tmp_path / "dark.jpg", brightness=20, add_edges=False)
    bright_path = _create_test_frame(tmp_path / "bright.jpg", brightness=220, add_edges=False)

    assessor = FrameQualityAssessor(CaptureConfig())
    res_dark, _ = assessor.evaluate_frame(dark_path)
    res_bright, _ = assessor.evaluate_frame(bright_path)

    assert res_dark.brightness == pytest.approx(20.0, abs=1.0)
    assert res_bright.brightness == pytest.approx(220.0, abs=1.0)
    assert res_dark.is_underexposed is True
    assert res_bright.is_overexposed is False  # default max is 235


def test_contrast_calculation(tmp_path: Path) -> None:
    """Verify contrast measurement tracks grayscale standard deviation."""
    flat_path = _create_test_frame(tmp_path / "flat.jpg", brightness=128, add_edges=False)
    contrasty_path = _create_test_frame(tmp_path / "contrasty.jpg", brightness=128, add_edges=True)

    assessor = FrameQualityAssessor(CaptureConfig())
    res_flat, _ = assessor.evaluate_frame(flat_path)
    res_contrasty, _ = assessor.evaluate_frame(contrasty_path)

    assert res_flat.contrast == pytest.approx(0.0, abs=0.5)
    assert res_contrasty.contrast > 20.0
    assert res_flat.is_low_contrast is True
    assert res_contrasty.is_low_contrast is False


def test_blur_rejection(tmp_path: Path) -> None:
    """Verify frames below sharpness_threshold are marked rejected with blur reason."""
    blurry_path = _create_test_frame(tmp_path / "blurry.jpg", blur_ksize=25)
    assessor = FrameQualityAssessor(CaptureConfig(sharpness_threshold=100.0))

    res, _ = assessor.evaluate_frame(blurry_path)

    assert res.is_blurry is True
    assert res.is_accepted is False
    assert any("sharpness" in r.lower() or "blur" in r.lower() for r in res.rejection_reasons)


def test_exposure_rejection(tmp_path: Path) -> None:
    """Verify underexposed and overexposed frames are rejected with exposure reasons."""
    dark_path = _create_test_frame(tmp_path / "very_dark.jpg", brightness=10, add_edges=False)
    over_path = _create_test_frame(tmp_path / "very_bright.jpg", brightness=250, add_edges=False)

    assessor = FrameQualityAssessor(CaptureConfig(min_brightness=30.0, max_brightness=235.0))

    res_dark, _ = assessor.evaluate_frame(dark_path)
    assert res_dark.is_underexposed is True
    assert res_dark.is_accepted is False
    assert any("Underexposed" in r for r in res_dark.rejection_reasons)

    res_over, _ = assessor.evaluate_frame(over_path)
    assert res_over.is_overexposed is True
    assert res_over.is_accepted is False
    assert any("Overexposed" in r for r in res_over.rejection_reasons)


def test_redundancy_filtering(tmp_path: Path) -> None:
    """Verify consecutive near-identical frames are rejected as redundant while shifted frames are kept."""
    f1 = _create_test_frame(tmp_path / "f1.jpg", brightness=128, add_edges=True, offset=0)
    f2_duplicate = _create_test_frame(tmp_path / "f2.jpg", brightness=128, add_edges=True, offset=0)

    # f3 has lines offset by 10 pixels (different visual structure)
    f3_different = _create_test_frame(tmp_path / "f3.jpg", brightness=128, add_edges=True, offset=10)

    assessor = FrameQualityAssessor(CaptureConfig(sharpness_threshold=10.0, redundancy_threshold=0.98))

    # Evaluate f1 (first frame -> accepted)
    res1, thumb1 = assessor.evaluate_frame(f1, None)
    assert res1.is_accepted is True
    assert res1.is_redundant is False

    # Evaluate f2 (identical to f1 -> rejected as redundant)
    res2, thumb2 = assessor.evaluate_frame(f2_duplicate, thumb1)
    assert res2.is_redundant is True
    assert res2.is_accepted is False
    assert any("Redundant" in r for r in res2.rejection_reasons)

    # Evaluate f3 (different from f1 -> accepted)
    res3, _ = assessor.evaluate_frame(f3_different, thumb2)
    assert res3.is_redundant is False
    assert res3.is_accepted is True


def test_assess_and_filter_sequence(tmp_path: Path) -> None:
    """Verify assess_and_filter aggregates results into CaptureAnalysisArtifact correctly."""
    f1 = _create_test_frame(tmp_path / "frame1.jpg", brightness=120, add_edges=True)
    f2 = _create_test_frame(tmp_path / "frame2.jpg", brightness=120, add_edges=True)  # redundant
    f3 = _create_test_frame(tmp_path / "frame3.jpg", blur_ksize=25)                    # blurry

    assessor = FrameQualityAssessor(CaptureConfig(sharpness_threshold=80.0, redundancy_threshold=0.98))
    artifact, results = assessor.assess_and_filter([f1, f2, f3])

    assert len(results) == 3
    assert f1 in artifact.selected_frames
    assert f2 in artifact.rejected_frames
    assert f3 in artifact.rejected_frames
    assert artifact.average_sharpness > 0.0
    assert len(artifact.guidance_notes) > 0
    assert artifact.metadata["total_candidate_frames"] == 3
    assert artifact.metadata["selected_count"] == 1
    assert artifact.metadata["rejected_count"] == 2
