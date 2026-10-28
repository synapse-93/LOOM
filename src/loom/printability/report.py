"""Printability analysis reporting interfaces and data structures."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from loom.config.models import PrintabilityConfig


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
    """Exports structured printability analysis reports and orchestrates checks."""

    @classmethod
    def generate_report(
        cls,
        mesh_path: Path | str,
        config: Optional[PrintabilityConfig] = None,
    ) -> PrintabilityReport:
        """Execute printability verification checks and return a structured report.

        Args:
            mesh_path: Path to target 3D mesh file.
            config: Optional printability configuration thresholds.

        Returns:
            Populated PrintabilityReport with check outcomes, warnings, and overall readiness.

        Raises:
            FileNotFoundError: If mesh_path does not exist.
        """
        p = Path(mesh_path).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"Mesh file not found for printability analysis: {p}")

        from loom.config.models import PrintabilityConfig
        from loom.printability.manifold import ManifoldChecker
        from loom.printability.overhang import OverhangAnalyzer
        from loom.printability.thickness import WallThicknessAnalyzer
        from loom.printability.watertight import WatertightChecker

        cfg = config or PrintabilityConfig()
        warnings: list[str] = []

        # 1. Watertight check
        is_watertight = False
        if cfg.check_watertight:
            try:
                is_watertight = WatertightChecker().is_watertight(p)
            except Exception as exc:
                warnings.append(f"Watertight check failed: {exc}")
                is_watertight = False
            if not is_watertight:
                warnings.append("Mesh is open/non-watertight; cannot form a sealed solid volume.")
        else:
            is_watertight = True

        # 2. Manifold check
        is_manifold = False
        if cfg.check_manifold:
            try:
                checker = ManifoldChecker()
                edge_manifold = checker.is_edge_manifold(p)
                vert_manifold = checker.is_vertex_manifold(p)
                is_manifold = edge_manifold and vert_manifold
            except Exception as exc:
                warnings.append(f"Manifold check failed: {exc}")
                is_manifold = False
            if not is_manifold:
                warnings.append("Mesh contains non-manifold edges or vertices.")
        else:
            is_manifold = True

        # 3. Overhang faces
        overhang_count = 0
        try:
            overhangs = OverhangAnalyzer().find_overhang_faces(
                p, max_overhang_angle_deg=cfg.max_overhang_angle_deg
            )
            overhang_count = len(overhangs)
            if overhang_count > 0:
                warnings.append(
                    f"{overhang_count} downward-facing surface elements require support structures at "
                    f">{cfg.max_overhang_angle_deg:.1f}°."
                )
        except Exception as exc:
            warnings.append(f"Overhang analysis failed: {exc}")

        # 4. Wall thickness (requires watertight solid)
        min_thickness: Optional[float] = None
        if is_watertight:
            try:
                min_thickness = WallThicknessAnalyzer().compute_minimum_thickness(p)
                if min_thickness < cfg.min_wall_thickness_mm:
                    warnings.append(
                        f"Estimated minimum wall thickness ({min_thickness:.2f} mm) is below "
                        f"configured threshold ({cfg.min_wall_thickness_mm:.2f} mm)."
                    )
            except Exception as exc:
                warnings.append(f"Wall thickness estimation failed: {exc}")
                min_thickness = None
        else:
            warnings.append(
                "Wall thickness analysis skipped: ray intersection requires a closed, watertight mesh."
            )

        # 5. Overall printability determination
        thickness_ok = min_thickness is not None and min_thickness >= cfg.min_wall_thickness_mm
        is_printable = is_watertight and is_manifold and thickness_ok

        return PrintabilityReport(
            is_watertight=is_watertight,
            is_manifold=is_manifold,
            min_wall_thickness_mm=min_thickness,
            overhang_face_count=overhang_count,
            is_printable=is_printable,
            warnings=warnings,
        )

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
