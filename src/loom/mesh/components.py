"""Connected component analysis and configurable component filtering."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import trimesh

from loom.config.models import MeshConfig
from loom.mesh.models import ComponentActionResult, ComponentInfo

logger = logging.getLogger(__name__)


class MeshComponentAnalyzer:
    """Inspector and filter for disconnected mesh fragments and clusters."""

    def __init__(self, config: Optional[MeshConfig] = None) -> None:
        self.config = config or MeshConfig()

    def analyze_components(
        self,
        mesh: Any = None,
    ) -> list[ComponentInfo]:
        """Analyze connected components (supports instance or class call)."""
        target_mesh = mesh if isinstance(self, MeshComponentAnalyzer) else self
        return MeshComponentAnalyzer.analyze(target_mesh)

    def filter_components(
        self,
        mesh: Any = None,
        config: Optional[MeshConfig] = None,
    ) -> tuple[trimesh.Trimesh, ComponentActionResult]:
        """Filter components using configured strategy (supports instance or class call)."""
        if isinstance(self, MeshComponentAnalyzer):
            target_mesh = mesh
            target_config = config or self.config
        else:
            target_mesh = self
            target_config = mesh if isinstance(mesh, MeshConfig) else (config or MeshConfig())
        return MeshComponentAnalyzer.filter(target_mesh, target_config)


    @classmethod
    def _split_submeshes(cls, mesh: trimesh.Trimesh) -> list[trimesh.Trimesh]:
        """Split mesh into connected components using face_adjacency without requiring networkx."""
        if len(mesh.faces) == 0:
            return []
        try:
            face_components = trimesh.graph.connected_components(mesh.face_adjacency)
            if len(face_components) == 0:
                return [mesh]
            return [mesh.submesh([c], append=True) for c in face_components]
        except Exception as exc:
            logger.warning("Connected component split failed: %s; falling back to single component.", exc)
            return [mesh]

    @classmethod
    def analyze(cls, mesh: trimesh.Trimesh) -> list[ComponentInfo]:
        """Split mesh into connected components and return diagnostic metrics for each."""
        if len(mesh.faces) == 0:
            return []

        submeshes = cls._split_submeshes(mesh)

        components: list[ComponentInfo] = []
        for idx, sub in enumerate(submeshes):
            v_count = len(sub.vertices)
            f_count = len(sub.faces)
            if v_count > 0:
                bb_min = tuple(float(x) for x in np.min(sub.vertices, axis=0))
                bb_max = tuple(float(x) for x in np.max(sub.vertices, axis=0))
            else:
                bb_min = (0.0, 0.0, 0.0)
                bb_max = (0.0, 0.0, 0.0)

            try:
                area_val = float(sub.area)
                area = area_val if not np.isnan(area_val) else 0.0
            except Exception:
                area = 0.0

            components.append(
                ComponentInfo(
                    index=idx,
                    vertex_count=v_count,
                    face_count=f_count,
                    bounding_box_min=bb_min,
                    bounding_box_max=bb_max,
                    surface_area=area,
                    is_kept=True,
                )
            )

        return components

    # Classmethod alias
    analyze_components = analyze

    @classmethod
    def filter(
        cls,
        mesh: trimesh.Trimesh,
        config: MeshConfig,
    ) -> tuple[trimesh.Trimesh, ComponentActionResult]:
        """Filter disconnected components based on configured strategy."""
        if len(mesh.faces) == 0:
            return mesh, ComponentActionResult(
                strategy=config.component_strategy,
                components_before=0,
                components_after=0,
                removed_components=0,
                removed_faces=0,
                removed_vertices=0,
            )

        submeshes = cls._split_submeshes(mesh)

        total_components = len(submeshes)
        if total_components <= 1:
            return mesh, ComponentActionResult(

                strategy=config.component_strategy,
                components_before=total_components,
                components_after=total_components,
                removed_components=0,
                removed_faces=0,
                removed_vertices=0,
            )

        strategy = config.component_strategy.lower()
        kept_submeshes: list[trimesh.Trimesh] = []
        details: list[dict[str, Any]] = []

        face_counts = [len(s.faces) for s in submeshes]
        max_faces = max(face_counts) if face_counts else 0

        areas: list[float] = []
        for s in submeshes:
            try:
                a = float(s.area)
                areas.append(a if not np.isnan(a) else 0.0)
            except Exception:
                areas.append(0.0)
        max_area = max(areas) if areas else 0.0

        for idx, sub in enumerate(submeshes):
            keep = False
            f_count = len(sub.faces)
            v_count = len(sub.vertices)
            sub_area = areas[idx]

            if strategy == "keep_all":
                keep = True
            elif strategy == "largest":
                keep = (f_count == max_faces)
            elif strategy == "largest_by_area":
                keep = (sub_area == max_area)
            elif strategy == "min_faces":
                keep = (f_count >= config.min_component_faces)
            elif strategy == "relative_threshold":
                keep = (f_count >= max_faces * config.min_component_ratio)
            else:
                # Default to keeping largest if unknown strategy specified
                logger.warning("Unknown component strategy '%s'; defaulting to 'largest'.", strategy)
                keep = (f_count == max_faces)

            if keep:
                kept_submeshes.append(sub)

            details.append({
                "index": idx,
                "vertex_count": v_count,
                "face_count": f_count,
                "surface_area": round(sub_area, 4),
                "is_kept": keep,
            })

        # Safeguard: Never delete the entire mesh; if all were filtered, keep the single largest
        if not kept_submeshes:
            logger.warning("Component filtering would remove all geometry. Preserving largest component.")
            largest_idx = int(np.argmax(face_counts))
            kept_submeshes = [submeshes[largest_idx]]
            details[largest_idx]["is_kept"] = True

        # Concatenate remaining submeshes into a single clean mesh
        if len(kept_submeshes) == 1:
            filtered_mesh = kept_submeshes[0]
        else:
            filtered_mesh = trimesh.util.concatenate(kept_submeshes)

        removed_components = total_components - len(kept_submeshes)
        removed_faces = len(mesh.faces) - len(filtered_mesh.faces)
        removed_vertices = len(mesh.vertices) - len(filtered_mesh.vertices)

        action_result = ComponentActionResult(
            strategy=strategy,
            components_before=total_components,
            components_after=len(kept_submeshes),
            removed_components=removed_components,
            removed_faces=max(0, removed_faces),
            removed_vertices=max(0, removed_vertices),
            component_details=details,
        )

        logger.info(
            "Component filtering (%s): kept %d/%d components (removed %d components, %d faces).",
            strategy,
            len(kept_submeshes),
            total_components,
            removed_components,
            removed_faces,
        )

        return filtered_mesh, action_result
