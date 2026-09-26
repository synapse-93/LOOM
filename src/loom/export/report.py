"""Job export summary report generator."""

from __future__ import annotations

from pathlib import Path
from loom.export.manifest import ExportManifest


class ExportReportGenerator:
    """Generates human-readable manufacturing reports accompanying exported STL."""

    @staticmethod
    def generate_summary(manifest: ExportManifest, output_path: Path) -> Path:
        """Write Markdown summary report for 3D printing operator."""
        p = Path(output_path).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        content = (
            f"# VIDEO2PRINT Manufacturing Job Summary\n\n"
            f"- **Project**: {manifest.project_name}\n"
            f"- **Model**: `{manifest.stl_filename}`\n"
            f"- **SHA-256**: `{manifest.file_sha256}`\n"
            f"- **Bounding Box**: {manifest.bounding_box_mm[0]:.2f} x "
            f"{manifest.bounding_box_mm[1]:.2f} x {manifest.bounding_box_mm[2]:.2f} {manifest.units}\n"
            f"- **Volume**: {manifest.volume_mm3:.2f} {manifest.units}^3\n"
            f"- **Watertight**: {'YES' if manifest.is_watertight else 'NO'}\n"
            f"- **Scale Multiplier**: {manifest.scale_factor_applied:.6f}\n"
            f"- **Generated At**: {manifest.created_at}\n"
        )
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return p
