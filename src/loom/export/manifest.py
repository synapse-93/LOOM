"""Export manifest data model and serialization."""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExportManifest:
    """Manufacturing build manifest describing exported 3D model and provenance."""

    project_name: str
    stl_filename: str
    file_sha256: str
    bounding_box_mm: tuple[float, float, float]
    volume_mm3: float
    is_watertight: bool
    scale_factor_applied: float
    units: str = "mm"
    created_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    def write_json(self, output_path: Path) -> Path:
        """Serialize manifest to JSON file."""
        p = Path(output_path).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "project_name": self.project_name,
            "stl_filename": self.stl_filename,
            "file_sha256": self.file_sha256,
            "bounding_box_mm": list(self.bounding_box_mm),
            "volume_mm3": self.volume_mm3,
            "is_watertight": self.is_watertight,
            "scale_factor_applied": self.scale_factor_applied,
            "units": self.units,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return p
