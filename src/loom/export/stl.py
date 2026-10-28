
"""STL model exporter."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh


class StlExporter:
    """Export surface meshes to binary or ASCII STL."""

    def export(
        self,
        mesh_path: Path,
        output_stl_path: Path,
        binary: bool = True,
    ) -> Path:
        """Export a mesh and verify its geometry and scale."""

        mesh_path = Path(mesh_path)
        output_stl_path = Path(output_stl_path)

        if not mesh_path.is_file():
            raise FileNotFoundError(f"Mesh file not found: {mesh_path}")

        mesh = trimesh.load(mesh_path, force="mesh", process=False)

        if not isinstance(mesh, trimesh.Trimesh):
            raise ValueError("Input file did not contain a valid mesh.")

        if len(mesh.vertices) == 0 or len(mesh.faces) == 0:
            raise ValueError("Cannot export an empty mesh.")

        output_stl_path.parent.mkdir(parents=True, exist_ok=True)

        if binary:
            output_stl_path.write_bytes(
                trimesh.exchange.stl.export_stl(mesh)
            )
        else:
            ascii_data = trimesh.exchange.stl.export_stl_ascii(mesh)
            output_stl_path.write_text(ascii_data, encoding="ascii")

        if not output_stl_path.is_file() or output_stl_path.stat().st_size == 0:
            raise RuntimeError("STL export failed or produced an empty file.")

        exported = trimesh.load(
            output_stl_path,
            force="mesh",
            process=False,
        )

        if not isinstance(exported, trimesh.Trimesh):
            raise RuntimeError("Exported STL could not be reloaded.")

        if len(exported.vertices) == 0 or len(exported.faces) == 0:
            raise RuntimeError("Exported STL contains no geometry.")

        if not np.allclose(
            mesh.bounds,
            exported.bounds,
            rtol=1e-5,
            atol=1e-7,
        ):
            raise RuntimeError("Exported STL changed mesh dimensions.")

        return output_stl_path
