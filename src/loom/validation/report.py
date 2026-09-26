"""Validation report generation interfaces."""

from __future__ import annotations

import json
from pathlib import Path
from loom.validation.comparison import GroundTruthComparison


class ValidationReportGenerator:
    """Generates structured Markdown and JSON reports for dimensional validation."""

    @staticmethod
    def generate_json_report(comparison: GroundTruthComparison, output_path: Path) -> Path:
        """Write validation comparison results to machine-readable JSON."""
        p = Path(output_path).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "target_name": comparison.target_name,
            "ground_truth_dimensions_mm": list(comparison.ground_truth_dimensions_mm),
            "reconstructed_dimensions_mm": list(comparison.reconstructed_dimensions_mm),
            "absolute_error_mm": list(comparison.absolute_error_mm),
            "relative_error_pct": list(comparison.relative_error_pct),
            "tolerance_threshold_mm": comparison.tolerance_threshold_mm,
            "passed": comparison.passed,
            "notes": comparison.notes,
        }
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return p

    def generate_markdown_report(self, comparison: GroundTruthComparison, output_path: Path) -> Path:
        """Generate human-readable Markdown validation summary report.

        Raises:
            NotImplementedError: Scheduled for Phase 5.
        """
        raise NotImplementedError("Markdown validation report generation scheduled for Phase 5.")
