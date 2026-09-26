"""Ground-truth dimensional comparison and error metric models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class GroundTruthComparison:
    """Comparison result of reconstructed model against calibrated ground truth."""

    target_name: str
    ground_truth_dimensions_mm: tuple[float, float, float]
    reconstructed_dimensions_mm: tuple[float, float, float]
    absolute_error_mm: tuple[float, float, float]
    relative_error_pct: tuple[float, float, float]
    tolerance_threshold_mm: float
    passed: bool
    notes: Optional[str] = None

    @classmethod
    def evaluate(
        cls,
        target_name: str,
        ground_truth: tuple[float, float, float],
        measured: tuple[float, float, float],
        tolerance_mm: float = 1.0,
    ) -> GroundTruthComparison:
        """Compute dimensional errors against physical ground truth.

        Note:
            Numerical values must originate from empirical measurements, not fabricated placeholders.
        """
        abs_err = (
            abs(measured[0] - ground_truth[0]),
            abs(measured[1] - ground_truth[1]),
            abs(measured[2] - ground_truth[2]),
        )
        rel_err = (
            (abs_err[0] / ground_truth[0]) * 100.0 if ground_truth[0] > 0 else 0.0,
            (abs_err[1] / ground_truth[1]) * 100.0 if ground_truth[1] > 0 else 0.0,
            (abs_err[2] / ground_truth[2]) * 100.0 if ground_truth[2] > 0 else 0.0,
        )
        passed = all(err <= tolerance_mm for err in abs_err)
        return cls(
            target_name=target_name,
            ground_truth_dimensions_mm=ground_truth,
            reconstructed_dimensions_mm=measured,
            absolute_error_mm=abs_err,
            relative_error_pct=rel_err,
            tolerance_threshold_mm=tolerance_mm,
            passed=passed,
        )
