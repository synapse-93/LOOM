
"""Minimum wall thickness estimation."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh


class WallThicknessAnalyzer:
    """Estimates wall thickness using rays through a mesh."""

    def compute_minimum_thickness(self, mesh_path: Path) -> float:
        """Estimate minimum thickness from intersections along face normals.

        The estimate uses inward rays from sampled surface points.
        Results are in the same units as the mesh coordinates.
        """
        mesh_path = Path(mesh_path)

        if not mesh_path.is_file():
            raise FileNotFoundError(f"Mesh file not found: {mesh_path}")

        mesh = trimesh.load(mesh_path, force="mesh", process=False)

        if not isinstance(mesh, trimesh.Trimesh):
            raise ValueError("Input file did not contain a valid mesh.")

        if len(mesh.faces) == 0 or len(mesh.vertices) < 4:
            raise ValueError("Mesh does not contain enough geometry.")

        if not np.isfinite(mesh.vertices).all():
            raise ValueError("Mesh contains non-finite coordinates.")

        if not mesh.is_watertight:
            raise ValueError("Wall thickness requires a watertight mesh.")

        # Sample face centers and cast rays inward from the surface.
        centers = np.asarray(mesh.triangles_center, dtype=float)
        normals = np.asarray(mesh.face_normals, dtype=float)

        if len(centers) == 0:
            raise ValueError("Mesh has no surface samples.")

        # Subsample large meshes to limit computation time.
        sample_count = min(500, len(centers))
        indices = np.linspace(
            0, len(centers) - 1, num=sample_count, dtype=int
        )

        centers = centers[indices]
        normals = normals[indices]

        bounds = mesh.bounds
        diagonal = float(np.linalg.norm(bounds[1] - bounds[0]))
        epsilon = max(diagonal * 1e-6, 1e-9)

        origins = centers - normals * epsilon
        directions = -normals

        locations, ray_indices, _ = mesh.ray.intersects_location(
            ray_origins=origins,
            ray_directions=directions,
            multiple_hits=True,
        )

        thicknesses = []

        for ray_index, location in zip(ray_indices, locations):
            distance = float(
                np.linalg.norm(location - origins[ray_index])
            )

            # Ignore near-zero self-intersections.
            if distance > epsilon * 10:
                thicknesses.append(distance)

        if not thicknesses:
            raise ValueError(
                "Could not estimate thickness; check mesh geometry and ray support."
            )

        return float(min(thicknesses))
