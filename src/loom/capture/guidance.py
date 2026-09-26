"""Adaptive capture guidance feedback generator."""

from __future__ import annotations

from typing import Optional, Sequence


class CaptureGuidance:
    """Generates actionable feedback for users based on capture analysis metrics."""

    @staticmethod
    def generate_recommendations(
        average_sharpness: float,
        blur_ratio: float,
        coverage_score: float,
        low_exposure_ratio: float = 0.0,
        redundancy_ratio: float = 0.0,
    ) -> list[str]:
        """Generate deterministic, human-readable capture guidance notes.

        Args:
            average_sharpness: Mean computed sharpness.
            blur_ratio: Fraction of frames discarded due to motion blur.
            coverage_score: Viewpoint / 2D frame diversity score.
            low_exposure_ratio: Fraction of frames with exposure/contrast defects.
            redundancy_ratio: Fraction of frames rejected as near-duplicates.

        Returns:
            List of actionable feedback messages.
        """
        recommendations: list[str] = []

        if blur_ratio > 0.4:
            recommendations.append("High motion blur detected. Move the camera more slowly around the object.")
        elif blur_ratio > 0.2:
            recommendations.append("Moderate motion blur observed in several frames. Stabilize camera movement.")

        if redundancy_ratio > 0.5:
            recommendations.append("Many frames are nearly identical. Move the camera farther between captures.")

        if low_exposure_ratio > 0.3:
            recommendations.append("Poor exposure or low contrast detected in multiple frames. Improve scene lighting.")

        if coverage_score < 0.6:
            recommendations.append("Low frame diversity detected. Ensure a continuous orbital trajectory around the target.")

        if not recommendations:
            recommendations.append("Capture quality is acceptable. Frame sequence is ready for 3D reconstruction.")

        return recommendations
