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
    def get_face_components(cls, mesh: trimesh.Trimesh) -> list[np.ndarray]:
        """Compute connected component face index arrays using face_adjacency directly.

        Sorts components by face count descending so Component #0 is always the largest.
        Never calls mesh.split() or allocates duplicate submeshes.
        """
        if len(mesh.faces) == 0:
            return []
        try:
            face_components = trimesh.graph.connected_components(mesh.face_adjacency)
            if len(face_components) == 0:
                face_components = [np.arange(len(mesh.faces))]
            return sorted(face_components, key=len, reverse=True)
        except Exception as exc:
            logger.warning("Connected components analysis failed: %s; using single component.", exc)
            return [np.arange(len(mesh.faces))]

    @classmethod
    def _split_submeshes(cls, mesh: trimesh.Trimesh) -> list[trimesh.Trimesh]:
        """Split mesh into connected components using face arrays without calling mesh.split()."""
        if len(mesh.faces) == 0:
            return []
        comps = cls.get_face_components(mesh)
        return [mesh.submesh([c], append=True) for c in comps]

    @classmethod
    def analyze(cls, mesh: trimesh.Trimesh) -> list[ComponentInfo]:
        """Split mesh into connected components and return diagnostic metrics for each.

        Uses face index arrays directly without heavy submesh allocations.
        """
        if len(mesh.faces) == 0:
            return []

        face_components = cls.get_face_components(mesh)

        try:
            face_areas = mesh.area_faces
        except Exception:
            face_areas = np.zeros(len(mesh.faces), dtype=np.float64)

        components: list[ComponentInfo] = []
        for idx, comp in enumerate(face_components):
            f_count = len(comp)
            comp_faces = mesh.faces[comp]
            unique_v = np.unique(comp_faces)
            v_count = len(unique_v)
            if v_count > 0:
                comp_verts = mesh.vertices[unique_v]
                bb_min = tuple(float(x) for x in np.min(comp_verts, axis=0))
                bb_max = tuple(float(x) for x in np.max(comp_verts, axis=0))
            else:
                bb_min = (0.0, 0.0, 0.0)
                bb_max = (0.0, 0.0, 0.0)

            area = float(np.sum(face_areas[comp])) if len(face_areas) > 0 else 0.0

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
        """Filter disconnected components based on configured strategy using memory-safe face arrays."""
        if len(mesh.faces) == 0:
            return mesh, ComponentActionResult(
                strategy=config.component_strategy,
                components_before=0,
                components_after=0,
                removed_components=0,
                removed_faces=0,
                removed_vertices=0,
            )

        face_components = cls.get_face_components(mesh)
        total_components = len(face_components)
        total_faces = len(mesh.faces)

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
        max_faces = len(face_components[0])

        # Component Selection Logic:
        # Identify components with > 100,000 faces (or > 20% of total mesh faces AND >= 1,000 faces for large models).
        large_component_indices = [
            i for i, c in enumerate(face_components)
            if len(c) > 100_000 or (total_faces >= 10_000 and len(c) > 0.20 * total_faces and len(c) >= 1_000)
        ]
        has_large_components = len(large_component_indices) > 0

        kept_indices: list[int] = []

        if strategy == "keep_all":
            kept_indices = list(range(total_components))

        elif strategy == "largest":
            # Component #0 is the primary object (the shoe)
            kept_indices = [0]

        elif strategy == "largest_by_area":
            try:
                face_areas = mesh.area_faces
                comp_areas = [float(np.sum(face_areas[c])) for c in face_components]
                kept_indices = [int(np.argmax(comp_areas))]
            except Exception:
                kept_indices = [0]

        elif strategy == "centroid_proximity":
            # Component Selection Logic:
            # - Identify components with > 100,000 faces (or > 20% of total mesh faces).
            # - Component #0 is the primary object (the shoe).
            # - Under NO circumstances should any component with < 1,000 faces be chosen as the target object when large components exist.
            if config.reference_point is None:
                # Component #0 is the primary object (the shoe)
                best_idx = 0
            else:
                ref_pt = np.asarray(config.reference_point, dtype=np.float64)
                if has_large_components:
                    # When large components exist, strictly exclude any component with < 1,000 faces
                    eligible = [i for i in large_component_indices if len(face_components[i]) >= 1_000]
                    if not eligible:
                        eligible = [0]
                else:
                    thresh = min(config.min_component_faces, max_faces)
                    eligible = [i for i, c in enumerate(face_components) if len(c) >= thresh]
                    if not eligible:
                        eligible = [0]

                min_dist = float("inf")
                best_idx = eligible[0]
                for idx in eligible:
                    comp = face_components[idx]
                    c_faces = mesh.faces[comp]
                    c_verts = mesh.vertices[np.unique(c_faces)]
                    centroid = np.mean(c_verts, axis=0)
                    if len(ref_pt) == 2:
                        dist = float(np.linalg.norm(centroid[:2] - ref_pt))
                    else:
                        dist = float(np.linalg.norm(centroid - ref_pt))
                    if dist < min_dist:
                        min_dist = dist
                        best_idx = idx

            kept_indices = [best_idx]

        elif strategy == "min_faces":
            kept_indices = [i for i, c in enumerate(face_components) if len(c) >= config.min_component_faces]

        elif strategy == "relative_threshold":
            kept_indices = [i for i, c in enumerate(face_components) if len(c) >= max_faces * config.min_component_ratio]

        else:
            logger.warning("Unknown component strategy '%s'; defaulting to 'largest'.", strategy)
            kept_indices = [0]

        if not kept_indices:
            logger.warning("Component filtering would remove all geometry. Preserving largest component.")
            kept_indices = [0]

        # Extract target mesh cleanly using submesh on face indices
        if len(kept_indices) == 1:
            target_faces = face_components[kept_indices[0]]
        else:
            target_faces = np.concatenate([face_components[i] for i in kept_indices])

        filtered_mesh = mesh.submesh([target_faces], append=True)

        # Build component details
        details: list[dict[str, Any]] = []
        for idx, comp in enumerate(face_components):
            details.append({
                "index": idx,
                "vertex_count": len(np.unique(mesh.faces[comp])),
                "face_count": len(comp),
                "is_kept": (idx in kept_indices),
            })

        removed_components = total_components - len(kept_indices)
        removed_faces = total_faces - len(filtered_mesh.faces)
        removed_vertices = len(mesh.vertices) - len(filtered_mesh.vertices)

        action_result = ComponentActionResult(
            strategy=strategy,
            components_before=total_components,
            components_after=len(kept_indices),
            removed_components=removed_components,
            removed_faces=max(0, removed_faces),
            removed_vertices=max(0, removed_vertices),
            component_details=details,
        )

        logger.info(
            "Component filtering (%s): kept %d/%d components (removed %d components, %d faces).",
            strategy,
            len(kept_indices),
            total_components,
            removed_components,
            removed_faces,
        )

        return filtered_mesh, action_result
