"""Deterministic invalid, degenerate, and unreferenced geometry cleanup."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import trimesh

from loom.config.models import MeshConfig
from loom.mesh.models import CleanupActionResult

logger = logging.getLogger(__name__)


class MeshCleaner:
    """Removes NaN/inf vertices, invalid indices, zero-area degenerate faces, and duplicate geometry."""

    def __init__(self, config: Optional[MeshConfig] = None) -> None:
        self.config = config or MeshConfig()

    def clean_mesh(
        self,
        mesh: Any = None,
        config: Optional[MeshConfig] = None,
    ) -> tuple[trimesh.Trimesh, CleanupActionResult]:
        """Clean mesh (supports instance or class call)."""
        if isinstance(self, MeshCleaner):
            target_mesh = mesh
            target_config = config or self.config
        else:
            target_mesh = self
            target_config = mesh if isinstance(mesh, MeshConfig) else (config or MeshConfig())
        return MeshCleaner.clean(target_mesh, target_config)

    @classmethod
    def clean(
        cls,
        mesh: trimesh.Trimesh,
        config: MeshConfig,
    ) -> tuple[trimesh.Trimesh, CleanupActionResult]:

        """Perform comprehensive deterministic cleanup of invalid, degenerate, and unreferenced geometry."""
        vertices = np.asarray(mesh.vertices, dtype=np.float64)
        faces = np.asarray(mesh.faces, dtype=np.int64)

        orig_v_count = len(vertices)
        orig_f_count = len(faces)

        invalid_vertices_removed = 0
        invalid_faces_removed = 0
        degenerate_faces_removed = 0
        duplicate_faces_removed = 0
        unreferenced_vertices_removed = 0

        # Step 1: Remove NaN and Infinite vertices
        nan_or_inf_mask = np.isnan(vertices).any(axis=1) | np.isinf(vertices).any(axis=1)
        invalid_v_indices = set(np.where(nan_or_inf_mask)[0])
        invalid_vertices_removed = len(invalid_v_indices)

        if invalid_vertices_removed > 0:
            logger.warning("Removing %d NaN or Infinite vertices and adjacent faces.", invalid_vertices_removed)
            valid_v_mask = ~nan_or_inf_mask
            # Build old-to-new vertex mapping (-1 for dropped)
            old_to_new = np.full(orig_v_count, -1, dtype=np.int64)
            old_to_new[valid_v_mask] = np.arange(np.sum(valid_v_mask))
            vertices = vertices[valid_v_mask]

            # Keep faces only if all 3 vertices are valid
            if len(faces) > 0:
                face_valid = ~np.isin(faces[:, 0], list(invalid_v_indices)) & \
                             ~np.isin(faces[:, 1], list(invalid_v_indices)) & \
                             ~np.isin(faces[:, 2], list(invalid_v_indices))
                dropped_faces = np.sum(~face_valid)
                invalid_faces_removed += int(dropped_faces)
                faces = old_to_new[faces[face_valid]]

        # Step 2: Remove invalid face indices
        if len(faces) > 0 and len(vertices) > 0:
            v_len = len(vertices)
            oob = (faces < 0) | (faces >= v_len)
            repeated = (
                (faces[:, 0] == faces[:, 1])
                | (faces[:, 1] == faces[:, 2])
                | (faces[:, 0] == faces[:, 2])
            )
            invalid_face_mask = np.any(oob, axis=1) | repeated
            invalid_f_count = int(np.sum(invalid_face_mask))
            if invalid_f_count > 0:
                logger.warning("Removing %d invalid or collapsed faces.", invalid_f_count)
                invalid_faces_removed += invalid_f_count
                faces = faces[~invalid_face_mask]

        # Step 3: Remove degenerate faces (zero-area triangles)
        if config.remove_degenerate_faces and len(faces) > 0 and len(vertices) > 0:
            v0 = vertices[faces[:, 0]]
            v1 = vertices[faces[:, 1]]
            v2 = vertices[faces[:, 2]]
            cross = np.cross(v1 - v0, v2 - v0)
            areas = 0.5 * np.linalg.norm(cross, axis=1)
            thresh = getattr(config, "degenerate_area_threshold", 1e-7)
            degenerate_mask = np.isnan(areas) | (areas <= thresh)
            degen_count = int(np.sum(degenerate_mask))
            if degen_count > 0:
                logger.info("Removing %d degenerate (zero-area) faces.", degen_count)
                degenerate_faces_removed += degen_count
                faces = faces[~degenerate_mask]

        # Step 4: Remove duplicate faces
        if config.remove_duplicate_faces and len(faces) > 0:
            sorted_f = np.sort(faces, axis=1)
            _, unique_indices = np.unique(sorted_f, axis=0, return_index=True)
            dup_count = len(faces) - len(unique_indices)
            if dup_count > 0:
                logger.info("Removing %d duplicate faces.", dup_count)
                duplicate_faces_removed += dup_count
                faces = faces[np.sort(unique_indices)]

        # Step 5: Remove unreferenced vertices
        if config.remove_unreferenced_vertices and len(vertices) > 0:
            if len(faces) > 0:
                unique_used = np.unique(faces)
                unref_count = len(vertices) - len(unique_used)
                if unref_count > 0:
                    logger.info("Removing %d unreferenced (orphaned) vertices.", unref_count)
                    unreferenced_vertices_removed += unref_count
                    remap = np.full(len(vertices), -1, dtype=np.int64)
                    remap[unique_used] = np.arange(len(unique_used))
                    vertices = vertices[unique_used]
                    faces = remap[faces]
            else:
                # No faces remain; unreferenced count is all vertices
                unreferenced_vertices_removed += len(vertices)
                vertices = np.empty((0, 3), dtype=np.float64)

        # Construct new cleaned mesh with strictly preserved coordinates
        cleaned_mesh = trimesh.Trimesh(
            vertices=vertices,
            faces=faces,
            process=False,  # Keep process=False to avoid unwanted auto-transformations
        )

        action_result = CleanupActionResult(
            invalid_vertices_removed=invalid_vertices_removed,
            invalid_faces_removed=invalid_faces_removed,
            degenerate_faces_removed=degenerate_faces_removed,
            duplicate_faces_removed=duplicate_faces_removed,
            unreferenced_vertices_removed=unreferenced_vertices_removed,
            vertices_before=orig_v_count,
            vertices_after=len(cleaned_mesh.vertices),
            faces_before=orig_f_count,
            faces_after=len(cleaned_mesh.faces),
        )


        logger.info(
            "Mesh cleanup complete: vertices %d -> %d, faces %d -> %d (invalid_v: %d, invalid_f: %d, degen: %d, dup: %d, unref: %d)",
            orig_v_count,
            len(cleaned_mesh.vertices),
            orig_f_count,
            len(cleaned_mesh.faces),
            invalid_vertices_removed,
            invalid_faces_removed,
            degenerate_faces_removed,
            duplicate_faces_removed,
            unreferenced_vertices_removed,
        )

        return cleaned_mesh, action_result

    # -------------------------------------------------------------------------
    # Backward compatibility with Phase 0 scaffold interface
    # -------------------------------------------------------------------------

    def remove_isolated_components(self, mesh_path: Path, output_path: Path, min_faces: int = 100) -> Path:
        """Remove floating disconnected triangle clusters smaller than min_faces."""
        loaded = trimesh.load(mesh_path, process=False)
        if isinstance(loaded, trimesh.Scene):
            loaded = trimesh.util.concatenate(list(loaded.geometry.values()))
        from loom.mesh.components import MeshComponentAnalyzer
        cfg = MeshConfig(component_strategy="min_faces", min_component_faces=min_faces)
        filtered, _ = MeshComponentAnalyzer.filter_components(loaded, cfg)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        filtered.export(output_path)
        return output_path

    def remove_unreferenced_vertices(self, mesh_path: Path, output_path: Path) -> Path:
        """Clean mesh by eliminating unreferenced vertices and zero-area faces."""
        loaded = trimesh.load(mesh_path, process=False)
        if isinstance(loaded, trimesh.Scene):
            loaded = trimesh.util.concatenate(list(loaded.geometry.values()))
        cfg = MeshConfig(remove_unreferenced_vertices=True, remove_degenerate_faces=True)
        cleaned, _ = self.clean(loaded, cfg)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cleaned.export(output_path)
        return output_path
