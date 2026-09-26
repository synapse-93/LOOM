"""Tests for printability verification interfaces and report generation."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from loom.printability.manifold import ManifoldChecker
from loom.printability.report import PrintabilityReport, PrintabilityReportGenerator
from loom.printability.watertight import WatertightChecker


def test_printability_report_export(tmp_path: Path) -> None:
    """Verify PrintabilityReport JSON serialization."""
    report = PrintabilityReport(
        is_watertight=True,
        is_manifold=True,
        min_wall_thickness_mm=1.5,
        overhang_face_count=12,
        is_printable=True,
        warnings=[],
    )

    out_file = tmp_path / "print_report.json"
    PrintabilityReportGenerator.export_json(report, out_file)
    assert out_file.is_file()

    with open(out_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["is_watertight"] is True
    assert data["min_wall_thickness_mm"] == 1.5


def test_manifold_and_watertight_checkers_raise_not_implemented() -> None:
    """Verify checkers raise NotImplementedError on scaffolded methods."""
    mc = ManifoldChecker()
    with pytest.raises(NotImplementedError):
        mc.is_edge_manifold(Path("mesh.obj"))

    wc = WatertightChecker()
    with pytest.raises(NotImplementedError):
        wc.is_watertight(Path("mesh.obj"))
