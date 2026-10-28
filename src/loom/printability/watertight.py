
"""Watertightness verification for 3D meshes."""

from __future__ import annotations

from pathlib import Path

import trimesh


class WatertightChecker:
    """Checks whether a mesh forms a closed volume."""

    def is_watertight(self, mesh_path: Path) -> bool:
        """Return True if the mesh is watertight and encloses positive volume."""

        mesh_path = Path(mesh_path)

        if not mesh_path.is_file():
            raise FileNotFoundError(f"Mesh file not found: {mesh_path}")

        mesh = trimesh.load(mesh_path, force="mesh", process=False)

        if not isinstance(mesh, trimesh.Trimesh):
            raise ValueError("Input file did not contain a valid mesh.")

        if len(mesh.vertices) == 0 or len(mesh.faces) == 0:
            return False

        return bool(mesh.is_watertight and mesh.is_volume and mesh.volume > 0)
