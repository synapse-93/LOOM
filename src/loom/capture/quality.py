"""Deterministic frame quality analysis, blur detection, and redundancy filtering."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
import cv2
import numpy as np

from loom.capture.guidance import CaptureGuidance
from loom.config.models import CaptureConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FrameQualityResult:
    """Detailed quality and selection metrics for a single image frame."""

    frame_path: Path
    sharpness: float
    brightness: float
    contrast: float
    is_blurry: bool
    is_underexposed: bool
    is_overexposed: bool
    is_low_contrast: bool
    is_redundant: bool
    is_accepted: bool
    rejection_reasons: tuple[str, ...]


class FrameQualityAssessor:
    """Evaluates optical sharpness, illumination, contrast, and visual redundancy."""

    def __init__(self, config: CaptureConfig) -> None:
        self.config = config

    def compute_sharpness(self, frame_path: Path) -> float:
        """Compute sharpness score via Laplacian variance on grayscale image.

        Args:
            frame_path: Path to target frame image.

        Returns:
            Calculated Laplacian variance (higher = sharper).
        """
        img = cv2.imread(str(frame_path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise ValueError(f"Unable to read frame image for quality analysis: {frame_path}")
        return float(cv2.Laplacian(img, cv2.CV_64F).var())

    def compute_brightness_and_contrast(self, frame_path: Path) -> tuple[float, float]:
        """Compute grayscale mean (brightness) and standard deviation (contrast).

        Args:
            frame_path: Path to image frame.

        Returns:
            Tuple of (brightness [0-255], contrast [0-255]).
        """
        img = cv2.imread(str(frame_path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise ValueError(f"Unable to read frame image for quality analysis: {frame_path}")
        return float(np.mean(img)), float(np.std(img))

    def evaluate_frame(
        self,
        frame_path: Path,
        prev_accepted_thumb: np.ndarray | None = None,
    ) -> tuple[FrameQualityResult, np.ndarray | None]:
        """Evaluate a single frame against all quality and redundancy thresholds.

        Args:
            frame_path: Path to candidate image frame.
            prev_accepted_thumb: Optional 64x64 thumbnail of the previous accepted frame.

        Returns:
            Tuple of (FrameQualityResult, current_frame_thumbnail_if_accepted).
        """
        gray = cv2.imread(str(frame_path), cv2.IMREAD_GRAYSCALE)
        if gray is None:
            raise ValueError(f"Failed to load image for quality assessment: {frame_path}")

        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        brightness = float(np.mean(gray))
        contrast = float(np.std(gray))

        reasons: list[str] = []

        is_blurry = sharpness < self.config.sharpness_threshold
        if is_blurry:
            reasons.append(
                f"Low sharpness ({sharpness:.1f} < threshold {self.config.sharpness_threshold:.1f})"
            )

        is_underexposed = brightness < getattr(self.config, "min_brightness", 30.0)
        if is_underexposed:
            reasons.append(f"Underexposed (brightness {brightness:.1f} < 30.0)")

        is_overexposed = brightness > getattr(self.config, "max_brightness", 235.0)
        if is_overexposed:
            reasons.append(f"Overexposed (brightness {brightness:.1f} > 235.0)")

        is_low_contrast = contrast < getattr(self.config, "min_contrast", 15.0)
        if is_low_contrast:
            reasons.append(f"Low contrast (std dev {contrast:.1f} < 15.0)")

        # Redundancy comparison using 64x64 normalized thumbnail
        thumb = cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA)
        is_redundant = False

        if prev_accepted_thumb is not None:
            # Mean absolute normalized difference in range [0.0, 1.0]
            diff = float(np.mean(np.abs(thumb.astype(float) - prev_accepted_thumb.astype(float)))) / 255.0
            similarity = 1.0 - diff
            redundancy_threshold = getattr(self.config, "redundancy_threshold", 0.98)
            if similarity >= redundancy_threshold:
                is_redundant = True
                reasons.append(
                    f"Redundant frame (similarity {similarity:.3f} >= threshold {redundancy_threshold:.3f})"
                )

        is_accepted = len(reasons) == 0
        new_thumb = thumb if is_accepted else prev_accepted_thumb

        result = FrameQualityResult(
            frame_path=frame_path,
            sharpness=round(sharpness, 2),
            brightness=round(brightness, 2),
            contrast=round(contrast, 2),
            is_blurry=is_blurry,
            is_underexposed=is_underexposed,
            is_overexposed=is_overexposed,
            is_low_contrast=is_low_contrast,
            is_redundant=is_redundant,
            is_accepted=is_accepted,
            rejection_reasons=tuple(reasons),
        )

        return result, new_thumb

    def assess_and_filter(
        self,
        frame_paths: Sequence[Path],
    ) -> tuple[CaptureAnalysisArtifact, list[FrameQualityResult]]:
        """Assess an entire sequence of candidate frames and select optimal keyframes.

        Args:
            frame_paths: Sequence of extracted frame paths.

        Returns:
            Tuple of (CaptureAnalysisArtifact, list of per-frame FrameQualityResult).
        """
        from loom.pipeline.artifacts import CaptureAnalysisArtifact

        results: list[FrameQualityResult] = []
        selected_frames: list[Path] = []
        rejected_frames: list[Path] = []

        prev_thumb: np.ndarray | None = None
        sharpness_values: list[float] = []

        blurry_count = 0
        exposure_count = 0
        redundant_count = 0

        for path in frame_paths:
            res, prev_thumb = self.evaluate_frame(path, prev_thumb)
            results.append(res)
            sharpness_values.append(res.sharpness)

            if res.is_blurry:
                blurry_count += 1
            if res.is_underexposed or res.is_overexposed or res.is_low_contrast:
                exposure_count += 1
            if res.is_redundant:
                redundant_count += 1

            if res.is_accepted:
                selected_frames.append(path)
            else:
                rejected_frames.append(path)

        avg_sharpness = float(np.mean(sharpness_values)) if sharpness_values else 0.0
        total_frames = max(1, len(frame_paths))
        blur_ratio = blurry_count / total_frames

        # 2D visual diversity / non-redundancy metric (NOT 3D surface coverage)
        diversity_score = round(len(selected_frames) / total_frames, 3)

        guidance_notes = CaptureGuidance.generate_recommendations(
            average_sharpness=avg_sharpness,
            blur_ratio=blur_ratio,
            coverage_score=diversity_score,
            low_exposure_ratio=exposure_count / total_frames,
            redundancy_ratio=redundant_count / total_frames,
        )

        logger.info(
            "Quality filter completed: %d total, %d selected, %d rejected (blurry: %d, exposure: %d, redundant: %d)",
            len(frame_paths),
            len(selected_frames),
            len(rejected_frames),
            blurry_count,
            exposure_count,
            redundant_count,
        )

        artifact = CaptureAnalysisArtifact(
            stage_name="capture_quality",
            selected_frames=selected_frames,
            rejected_frames=rejected_frames,
            average_sharpness=round(avg_sharpness, 2),
            coverage_score=diversity_score,
            guidance_notes=guidance_notes,
            metadata={
                "total_candidate_frames": len(frame_paths),
                "selected_count": len(selected_frames),
                "rejected_count": len(rejected_frames),
                "blurry_count": blurry_count,
                "exposure_defect_count": exposure_count,
                "redundant_count": redundant_count,
                "diversity_score": diversity_score,
                "thresholds": {
                    "sharpness": self.config.sharpness_threshold,
                    "min_brightness": getattr(self.config, "min_brightness", 30.0),
                    "max_brightness": getattr(self.config, "max_brightness", 235.0),
                    "min_contrast": getattr(self.config, "min_contrast", 15.0),
                    "redundancy_threshold": getattr(self.config, "redundancy_threshold", 0.98),
                },
            },
        )

        return artifact, results

    def filter_keyframes(self, frame_paths: Sequence[Path]) -> tuple[list[Path], list[Path]]:
        """Separate candidate frames into accepted and rejected lists (convenience helper)."""
        artifact, _ = self.assess_and_filter(frame_paths)
        return artifact.selected_frames, artifact.rejected_frames
