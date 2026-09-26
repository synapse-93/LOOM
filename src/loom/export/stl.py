"""STL binary model exporter interface."""

from __future__ import annotations

from pathlib import Path


class StlExporter:
    """Interface for exporting validated surface meshes to binary STL."""

    def export(self, mesh_path: Path, output_stl_path: Path, binary: bool = True) -> Path:
        """Export mesh to STL format.

        Raises:
            NotImplementedError: Scheduled for Phase 6.
        """
        raise NotImplementedError("STL export scheduled for Phase 6.")
