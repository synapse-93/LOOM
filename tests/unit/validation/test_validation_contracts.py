"""Tests for validation and error metric models."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from loom.validation.comparison import GroundTruthComparison
from loom.validation.report import ValidationReportGenerator


def test_ground_truth_comparison_evaluation() -> None:
    """Verify GroundTruthComparison calculates absolute and relative errors accurately."""
    gt = (50.0, 50.0, 50.0)
    measured = (50.5, 49.0, 50.2)

    comp = GroundTruthComparison.evaluate(
        target_name="test_cube",
        ground_truth=gt,
        measured=measured,
        tolerance_mm=1.0,
    )

    assert comp.target_name == "test_cube"
    assert comp.passed is True
    assert pytest.approx(comp.absolute_error_mm[0], 0.01) == 0.5
    assert pytest.approx(comp.absolute_error_mm[1], 0.01) == 1.0
    assert pytest.approx(comp.absolute_error_mm[2], 0.01) == 0.2


def test_validation_report_export(tmp_path: Path) -> None:
    """Verify JSON export of validation metrics."""
    gt = (100.0, 100.0, 100.0)
    measured = (102.0, 100.0, 99.0)
    comp = GroundTruthComparison.evaluate("box", gt, measured, tolerance_mm=1.0)
    assert comp.passed is False  # 102.0 exceeds 1.0mm tolerance

    report_path = tmp_path / "val_report.json"
    out = ValidationReportGenerator.generate_json_report(comp, report_path)
    assert out.is_file()

    with open(out, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["target_name"] == "box"
    assert data["passed"] is False
    assert data["absolute_error_mm"][0] == 2.0
