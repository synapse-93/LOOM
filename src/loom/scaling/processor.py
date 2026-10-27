import json
import os
from dataclasses import asdict
import trimesh
from .models import ScaleConfig, ScaleResult
from .transform import apply_mesh_scale

class MetricScalingProcessor:
    """Coordinates metric scaling transformation and JSON output reporting."""
    def __init__(self, config: ScaleConfig):
        self.config = config

    def process(self, mesh: trimesh.Trimesh, reconstructed_marker_size: float) -> tuple[trimesh.Trimesh, ScaleResult]:
        """Calculates scale factor s = physical_mm / reconstructed_units and scales the mesh."""
        if reconstructed_marker_size <= 0:
            result = ScaleResult(
                scale_factor=1.0,
                original_bounding_box=tuple(mesh.extents),
                scaled_bounding_box=tuple(mesh.extents),
                success=False,
                error_message="Invalid reconstructed marker size. Must be greater than 0."
            )
            return mesh, result

        scale_factor = self.config.marker_size_mm / reconstructed_marker_size
        scaled_mesh = apply_mesh_scale(mesh, scale_factor)

        result = ScaleResult(
            scale_factor=scale_factor,
            original_bounding_box=tuple(mesh.extents),
            scaled_bounding_box=tuple(scaled_mesh.extents),
            success=True
        )
        return scaled_mesh, result

    def save_report(self, result: ScaleResult, output_dir: str, filename: str = "scaling_report.json") -> str:
        """Saves scaling outcome details to a machine-readable JSON report."""
        os.makedirs(output_dir, exist_ok=True)
        report_path = os.path.join(output_dir, filename)
        
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(asdict(result), f, indent=4)
            
        return report_path