"""Printability analysis reporting interfaces and data structures."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class PrintabilityReport:
    """Detailed summary of 3D manufacturing readiness checks."""

    is_watertight: bool
    is_manifold: bool
    min_wall_thickness_mm: Optional[float]
    overhang_face_count: int
    is_printable: bool
    warnings: list[str]


class PrintabilityReportGenerator:
    """Exports structured printability analysis reports."""

    @staticmethod
    def export_json(report: PrintabilityReport, output_path: Path) -> Path:
        """Write printability report to JSON."""
        p = Path(output_path).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "is_watertight": report.is_watertight,
            "is_manifold": report.is_manifold,
            "min_wall_thickness_mm": report.min_wall_thickness_mm,
            "overhang_face_count": report.overhang_face_count,
            "is_printable": report.is_printable,
            "warnings": report.warnings,
        }
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return p
