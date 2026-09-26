"""Adaptive capture guidance feedback generator."""

from __future__ import annotations

from typing import Sequence


class CaptureGuidance:
    """Generates actionable feedback for users based on capture analysis metrics."""

    @staticmethod
    def generate_recommendations(
        average_sharpness: float,
        blur_ratio: float,
        coverage_score: float,
    ) -> list[str]:
        """Generate human-readable capture guidance notes.

        Args:
            average_sharpness: Mean computed sharpness.
            blur_ratio: Fraction of frames discarded due to motion blur.
            coverage_score: Viewpoint coverage score.

        Returns:
            List of actionable feedback messages.
        """
        recommendations: list[str] = []
        if blur_ratio > 0.4:
            recommendations.append("High motion blur detected. Move smartphone more slowly around object.")
        if coverage_score < 0.7:
            recommendations.append("Incomplete viewpoint coverage. Capture complete orbital trajectory including top hemisphere.")
        return recommendations
