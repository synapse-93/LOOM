"""STL binary model exporter interface with printability gate enforcement and manifest generation."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional
import trimesh

from loom.config.models import ExportConfig
from loom.export.manifest import ExportManifest
from loom.printability.exceptions import PrintabilityValidationError
from loom.printability.gate import PrintabilityGate, PrintabilityValidationResult
from loom.validation.dimensions import DimensionAnalyzer
from loom.utils.logging import get_logger

logger = get_logger("loom.export.stl")


class StlExporter:
    """Exports validated surface meshes to binary STL with manufacturing readiness checks and manifests."""

    def __init__(
        self,
        config: Optional[ExportConfig] = None,
        enforce_printability_gate: bool = True,
    ) -> None:
        self.config = config or ExportConfig()
        self.enforce_printability_gate = enforce_printability_gate
        self._gate = PrintabilityGate()
        self._dimension_analyzer = DimensionAnalyzer()
        self.last_manifest: Optional[ExportManifest] = None
        self.last_manifest_path: Optional[Path] = None
        self.last_validation_result: Optional[PrintabilityValidationResult] = None

    @staticmethod
    def _load_mesh(mesh_input: Path | str | trimesh.Trimesh) -> trimesh.Trimesh:
        """Load and resolve a trimesh.Trimesh instance from a path or object."""
        if isinstance(mesh_input, trimesh.Trimesh):
            return mesh_input
        p = Path(mesh_input).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"Input mesh file does not exist: {p}")
        loaded = trimesh.load(str(p), process=False)
        if isinstance(loaded, trimesh.Scene):
            if len(loaded.geometry) == 0:
                raise ValueError(f"Mesh file contains no geometry: {p}")
            return trimesh.util.concatenate(list(loaded.geometry.values()))
        return loaded

    @staticmethod
    def _compute_sha256(file_path: Path) -> str:
        """Calculate SHA-256 checksum of an exported file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def export(
        self,
        mesh_path: Path | str | trimesh.Trimesh,
        output_stl_path: Optional[Path | str] = None,
        binary: bool = True,
        manifest_path: Optional[Path | str] = None,
        scale_factor_applied: float = 1.0,
        project_name: str = "LOOM",
        enforce_gate: Optional[bool] = None,
        validation_result: Optional[PrintabilityValidationResult] = None,
    ) -> Path:
        """Export mesh to binary STL, enforcing the printability gate and writing a JSON manifest.

        Args:
            mesh_path: Input mesh file path or loaded Trimesh instance.
            output_stl_path: Destination path for STL (defaults to outputs/stl/<model_name>_metric.stl).
            binary: Whether to export in binary STL format (default: True).
            manifest_path: Destination path for manifest JSON (defaults to <stl_path_stem>_manifest.json).
            scale_factor_applied: Scaling multiplier applied to the mesh (default: 1.0).
            project_name: Project/model name for metadata (default: 'LOOM').
            enforce_gate: Override for printability gate enforcement (defaults to self.enforce_printability_gate).
            validation_result: Optional precomputed validation result to avoid redundant evaluations.

        Returns:
            Resolved Path to the exported binary STL file.

        Raises:
            FileNotFoundError: If input mesh path does not exist.
            PrintabilityValidationError: If mesh fails manufacturing readiness gate (when enforce_gate is True).
            ValueError: If mesh contains 0 vertices or faces.
        """
        mesh = self._load_mesh(mesh_path)
        should_enforce = (
            enforce_gate if enforce_gate is not None else self.enforce_printability_gate
        )

        # 1. Evaluate Printability Gate
        if validation_result is None:
            if not should_enforce and self.last_validation_result is not None:
                validation_result = self.last_validation_result
            else:
                validation_result = self._gate.validate(mesh)
        self.last_validation_result = validation_result

        if should_enforce and not validation_result.passed:
            err_msg = "; ".join(validation_result.errors)
            mesh_name = Path(mesh_path).name if isinstance(mesh_path, (str, Path)) else "mesh"
            logger.error("Mesh '%s' failed printability validation gate: %s", mesh_name, err_msg)
            raise PrintabilityValidationError(
                f"Mesh '{mesh_name}' failed printability validation: {err_msg}",
                validation_result=validation_result,
            )

        # 2. Determine Output STL Destination Path
        resolved_stl: Path
        if output_stl_path is not None:
            p_out = Path(output_stl_path).resolve()
            if p_out.is_dir() or p_out.suffix.lower() != ".stl":
                base_name = Path(mesh_path).stem if isinstance(mesh_path, (str, Path)) else "model"
                clean_base = base_name.replace("_scaled", "").replace("_cleaned", "")
                resolved_stl = p_out / f"{clean_base}_metric.stl"
            else:
                resolved_stl = p_out
        else:
            base_name = Path(mesh_path).stem if isinstance(mesh_path, (str, Path)) else "model"
            clean_base = base_name.replace("_scaled", "").replace("_cleaned", "")
            resolved_stl = self.config.output_dir.resolve() / f"{clean_base}_metric.stl"

        resolved_stl.parent.mkdir(parents=True, exist_ok=True)

        # 3. Export binary STL
        export_bytes = mesh.export(file_type="stl")
        if isinstance(export_bytes, str):
            export_bytes = export_bytes.encode("utf-8")
        resolved_stl.write_bytes(export_bytes)
        logger.info(
            "Exported %s STL (%d faces, %d bytes) to %s",
            "binary" if binary else "ascii",
            len(mesh.faces),
            len(export_bytes),
            resolved_stl,
        )

        # 4. Compute Geometry & Bounding Metrics for Manifest
        sha256_hash = self._compute_sha256(resolved_stl)
        obb_dimensions = self._dimension_analyzer.compute_principal_dimensions(mesh)
        volume_mm3 = validation_result.volume_mm3
        triangle_count = validation_result.triangle_count

        # 5. Generate and Write JSON Manifest
        resolved_manifest: Path
        if manifest_path is not None:
            resolved_manifest = Path(manifest_path).resolve()
        else:
            resolved_manifest = resolved_stl.parent / f"{resolved_stl.stem}_manifest.json"

        manifest = ExportManifest(
            project_name=project_name,
            stl_filename=resolved_stl.name,
            file_sha256=sha256_hash,
            bounding_box_mm=obb_dimensions,
            volume_mm3=volume_mm3,
            is_watertight=validation_result.is_watertight,
            scale_factor_applied=scale_factor_applied,
            triangle_count=triangle_count,
            units="mm",
            metadata={
                "boundary_edge_count": validation_result.boundary_edge_count,
                "non_manifold_edge_count": validation_result.non_manifold_edge_count,
                "non_manifold_vertex_count": validation_result.non_manifold_vertex_count,
                "vertex_count": validation_result.vertex_count,
                "is_positive_volume": validation_result.is_positive_volume,
                "printability_gate_passed": validation_result.passed,
            },
        )
        manifest.write_json(resolved_manifest)
        self.last_manifest = manifest
        self.last_manifest_path = resolved_manifest

        logger.info(
            "Export manifest generated: %s (BB: %.1fx%.1fx%.1f mm, Vol: %.1f mm^3, Triangles: %d)",
            resolved_manifest.name,
            obb_dimensions[0],
            obb_dimensions[1],
            obb_dimensions[2],
            volume_mm3,
            triangle_count,
        )

        return resolved_stl
