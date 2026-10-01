"""Metric mesh transformation and coordinate rescaling module."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Sequence
import numpy as np
import trimesh

from loom.scaling.exceptions import MeshScalingError
from loom.utils.logging import get_logger

logger = get_logger("loom.scaling.transform")


class ScaleTransformer:
    """Applies metric scaling transformations to 3D mesh vertices while strictly preserving topology."""

    @staticmethod
    def transform_vertices(
        vertices: np.ndarray,
        scale_factor: float,
        origin: tuple[float, float, float] | Sequence[float] | np.ndarray = (0.0, 0.0, 0.0),
    ) -> np.ndarray:
        """Deterministically scale 3D vertex coordinates around an explicit transformation origin.

        Formula:
            scaled_position = origin + scale_factor * (position - origin)

        Args:
            vertices: Nx3 numpy array of vertex coordinates.
            scale_factor: Positive scalar multiplier.
            origin: 3D point about which scaling is applied (default: (0, 0, 0)).

        Returns:
            Nx3 numpy array of scaled vertex coordinates.

        Raises:
            ValueError: If scale_factor <= 0 or non-finite.
        """
        try:
            s = float(scale_factor)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Scale factor must be numeric, got {scale_factor}") from exc

        if not math.isfinite(s) or s <= 0.0:
            raise ValueError(f"Scale factor must be strictly positive (> 0.0) and finite, got {scale_factor}")

        origin_arr = np.asarray(origin, dtype=np.float64).reshape((1, 3))
        if not np.all(np.isfinite(origin_arr)):
            raise ValueError(f"Transformation origin contains non-finite coordinates: {origin}")

        verts = np.asarray(vertices, dtype=np.float64)
        if len(verts.shape) != 2 or verts.shape[1] != 3:
            raise ValueError(f"Vertices array must be Nx3, got shape {verts.shape}")

        # Deterministic linear scaling about origin
        scaled_verts = origin_arr + s * (verts - origin_arr)
        return scaled_verts

    def transform_mesh(
        self,
        mesh: trimesh.Trimesh,
        scale_factor: float,
        origin: tuple[float, float, float] | Sequence[float] | np.ndarray = (0.0, 0.0, 0.0),
    ) -> trimesh.Trimesh:
        """Transform mesh geometry by applying scale factor while keeping faces and topology identical.

        Args:
            mesh: Trimesh instance.
            scale_factor: Positive scalar multiplier.
            origin: Explicit transformation center (default: (0, 0, 0)).

        Returns:
            New Trimesh instance with scaled coordinates and identical face indexing.
        """
        if mesh is None or len(mesh.vertices) == 0:
            raise MeshScalingError("Cannot transform empty mesh.")

        scaled_vertices = self.transform_vertices(mesh.vertices, scale_factor, origin=origin)

        # Create copy and update vertices without running Trimesh processing/merging
        scaled_mesh = mesh.copy()
        scaled_mesh.vertices = scaled_vertices
        return scaled_mesh

    def apply_scale(
        self,
        mesh_path: Path | str,
        scale_factor: float,
        output_path: Path | str,
        origin: tuple[float, float, float] | Sequence[float] | np.ndarray = (0.0, 0.0, 0.0),
    ) -> Path:
        """Load 3D mesh, scale vertices deterministically, and export to destination path.

        Args:
            mesh_path: Input mesh file (.obj, .ply, .stl).
            scale_factor: Positive scalar multiplier.
            output_path: Output mesh destination file path.
            origin: Explicit transformation origin (default: (0, 0, 0)).

        Returns:
            Resolved Path to scaled mesh file.

        Raises:
            FileNotFoundError: If input mesh file does not exist.
            ValueError: If scale_factor <= 0.
            MeshScalingError: If mesh cannot be loaded or exported.
        """
        # Validation of scale_factor
        try:
            s = float(scale_factor)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Scale factor must be numeric, got {scale_factor}") from exc
        if not math.isfinite(s) or s <= 0.0:
            raise ValueError(f"Scale factor must be strictly positive, got {scale_factor}")

        input_file = Path(mesh_path).resolve()
        if not input_file.is_file():
            raise FileNotFoundError(f"Input mesh file does not exist: {input_file}")


        try:
            # process=False ensures Trimesh does not alter topology, merge vertices, or normalize
            loaded = trimesh.load(input_file, process=False)
            if isinstance(loaded, trimesh.Scene):
                if len(loaded.geometry) == 0:
                    raise MeshScalingError("Loaded mesh scene contains no geometry.")
                mesh = trimesh.util.concatenate(list(loaded.geometry.values()))
            else:
                mesh = loaded
        except Exception as exc:
            raise MeshScalingError(f"Failed to load mesh from {input_file}: {exc}") from exc

        scaled_mesh = self.transform_mesh(mesh, s, origin=origin)

        destination = Path(output_path).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)

        try:
            scaled_mesh.export(str(destination))
        except Exception as exc:
            raise MeshScalingError(f"Failed to export scaled mesh to {destination}: {exc}") from exc

        logger.info(
            "Successfully scaled mesh '%s' -> '%s' (scale=%.6f, vertices=%d, faces=%d)",
            input_file.name,
            destination.name,
            s,
            len(scaled_mesh.vertices),
            len(scaled_mesh.faces),
        )
        return destination
