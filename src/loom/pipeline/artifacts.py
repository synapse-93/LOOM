"""Typed artifact data models representing intermediate and terminal pipeline outputs."""

from __future__ import annotations

import datetime
import logging
import shutil
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from loom.utils.paths import ensure_directory

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BaseArtifact:
    """Base class for all immutable pipeline artifacts."""

    stage_name: str
    created_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VideoArtifact(BaseArtifact):
    """Artifact representing an ingested and validated source video."""

    video_path: Path = field(default_factory=lambda: Path())
    duration_seconds: float = 0.0
    frame_count: int = 0
    resolution: tuple[int, int] = (0, 0)
    fps: float = 0.0


@dataclass(frozen=True)
class FrameSetArtifact(BaseArtifact):
    """Artifact representing a set of extracted video frames."""

    frames_dir: Path = field(default_factory=lambda: Path())
    frame_paths: list[Path] = field(default_factory=list)
    total_extracted: int = 0


@dataclass(frozen=True)
class CaptureAnalysisArtifact(BaseArtifact):
    """Artifact representing visual quality and coverage analysis of frames."""

    selected_frames: list[Path] = field(default_factory=list)
    rejected_frames: list[Path] = field(default_factory=list)
    average_sharpness: float = 0.0
    coverage_score: float = 0.0
    guidance_notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReconstructionArtifact(BaseArtifact):
    """Artifact representing raw photogrammetry output (mesh and camera trajectory)."""

    mesh_path: Optional[Path] = None
    sparse_reconstruction_path: Optional[Path] = None
    dense_point_cloud_path: Optional[Path] = None
    point_cloud_path: Optional[Path] = None
    camera_poses_path: Optional[Path] = None
    backend_name: str = "unknown"
    execution_time_seconds: float = 0.0
    sparse_points_path: Optional[Path] = None
    fused_point_cloud_path: Optional[Path] = None
    raw_mesh_path: Optional[Path] = None
    point_count: Optional[int] = None
    point_density: Optional[float] = None
    insufficient_coverage_warning: bool = False
    checkpoints_dir: Optional[Path] = None
    checkpoints: dict[str, Path] = field(default_factory=dict)


@dataclass(frozen=True)
class ReconstructionCheckpointsArtifact(BaseArtifact):
    """Artifact representing intermediate reconstruction checkpoint outputs.

    Preserves visibility into intermediate outputs:
        - 01_sparse/points3D.ply (sparse feature points)
        - 02_dense/fused.ply (dense fused point cloud)
        - 03_raw_mesh/meshed-poisson.ply (untrimmed Poisson mesh)
    """

    run_name: str = ""
    reconstruction_dir: Path = field(default_factory=lambda: Path())
    sparse_points_path: Optional[Path] = None
    dense_point_cloud_path: Optional[Path] = None
    raw_mesh_path: Optional[Path] = None
    floor_removed_mesh_path: Optional[Path] = None
    base_capped_mesh_path: Optional[Path] = None
    point_count: int = 0
    point_density: float = 0.0
    insufficient_coverage_warning: bool = False
    min_points_threshold: int = 50000

    @property
    def is_dense_sufficient(self) -> bool:
        """Return True if fused point count meets or exceeds the threshold."""
        return self.point_count >= self.min_points_threshold


@dataclass(frozen=True)
class PointCloudArtifact(BaseArtifact):
    """Artifact representing a cleaned or filtered 3D point cloud."""

    point_cloud_path: Path = field(default_factory=lambda: Path())
    point_count: int = 0


@dataclass(frozen=True)
class MeshArtifact(BaseArtifact):
    """Artifact representing a processed 3D surface mesh."""

    mesh_path: Path = field(default_factory=lambda: Path())
    vertex_count: int = 0
    face_count: int = 0
    is_cleaned: bool = False


@dataclass(frozen=True)
class ScaledMeshArtifact(BaseArtifact):
    """Artifact representing a metrically scaled 3D mesh."""

    mesh_path: Path = field(default_factory=lambda: Path())
    scale_factor: float = 1.0
    units: str = "mm"
    marker_detected: bool = False


@dataclass(frozen=True)
class ValidationArtifact(BaseArtifact):
    """Artifact representing dimensional comparison against ground truth."""

    report_path: Path = field(default_factory=lambda: Path())
    absolute_error_mm: Optional[float] = None
    relative_error_pct: Optional[float] = None
    passed: bool = False


@dataclass(frozen=True)
class PrintabilityArtifact(BaseArtifact):
    """Artifact representing manufacturing readiness and 3D print check results."""

    report_path: Path = field(default_factory=lambda: Path())
    is_watertight: bool = False
    is_manifold: bool = False
    min_thickness_mm: Optional[float] = None
    printable: bool = False


@dataclass(frozen=True)
class ExportArtifact(BaseArtifact):
    """Artifact representing final exported manufacturing models and manifest."""

    stl_path: Path = field(default_factory=lambda: Path())
    manifest_path: Path = field(default_factory=lambda: Path())
    file_size_bytes: int = 0


# =============================================================================
# Intermediate Checkpoint Helpers & Point Cloud Diagnostics
# =============================================================================


def read_ply_vertex_count(ply_path: Path | str) -> int:
    """Read vertex count directly from a PLY file header (ASCII or binary).

    Args:
        ply_path: Path to .ply file.

    Returns:
        Integer count of vertices, or 0 if unreadable.
    """
    p = Path(ply_path)
    if not p.is_file():
        return 0
    try:
        with open(p, "rb") as f:
            for _ in range(250):
                line = f.readline()
                if not line:
                    break
                line_str = line.decode("ascii", errors="ignore").strip()
                if line_str.startswith("element vertex"):
                    parts = line_str.split()
                    if len(parts) >= 3:
                        try:
                            return int(parts[2])
                        except ValueError:
                            pass
                if line_str == "end_header":
                    break
    except Exception as exc:
        logger.debug("Failed reading PLY vertex count from %s: %s", p, exc)
    return 0


def compute_ply_density(
    ply_path: Path | str,
    point_count: int | None = None,
    sample_limit: int = 10000,
) -> float:
    """Compute spatial point density (points per cubic unit) from a PLY file.

    Evaluates coordinates from the PLY body to establish bounding box volume V,
    and returns point_count / V. If V is 0 or degenerate, returns float(point_count).

    Args:
        ply_path: Path to .ply file.
        point_count: Optional pre-parsed vertex count.
        sample_limit: Maximum vertices to sample for bounding box calculation.

    Returns:
        Density value as a float.
    """
    p = Path(ply_path)
    if not p.is_file():
        return 0.0

    if point_count is None:
        point_count = read_ply_vertex_count(p)

    if point_count == 0:
        return 0.0

    min_x = min_y = min_z = float("inf")
    max_x = max_y = max_z = float("-inf")
    points_read = 0

    try:
        with open(p, "rb") as f:
            is_ascii = True
            is_binary_le = False
            vertex_properties: list[tuple[str, str]] = []
            in_vertex = False

            while True:
                line = f.readline()
                if not line:
                    break
                line_str = line.decode("ascii", errors="ignore").strip()
                if line_str.startswith("format"):
                    if "ascii" in line_str:
                        is_ascii = True
                    elif "binary_little_endian" in line_str:
                        is_binary_le = True
                        is_ascii = False
                elif line_str.startswith("element vertex"):
                    in_vertex = True
                elif line_str.startswith("element ") and in_vertex:
                    in_vertex = False
                elif in_vertex and line_str.startswith("property"):
                    parts = line_str.split()
                    if len(parts) >= 3:
                        vertex_properties.append((parts[1], parts[2]))
                elif line_str == "end_header":
                    break

            if is_ascii:
                for line in f:
                    if points_read >= sample_limit:
                        break
                    parts = line.decode("ascii", errors="ignore").strip().split()
                    if len(parts) >= 3:
                        try:
                            x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
                            min_x, max_x = min(min_x, x), max(max_x, x)
                            min_y, max_y = min(min_y, y), max(max_y, y)
                            min_z, max_z = min(min_z, z), max(max_z, z)
                            points_read += 1
                        except ValueError:
                            continue
            elif is_binary_le and vertex_properties:
                type_map = {
                    "float": ("f", 4),
                    "float32": ("f", 4),
                    "double": ("d", 8),
                    "float64": ("d", 8),
                    "uchar": ("B", 1),
                    "uint8": ("B", 1),
                    "char": ("b", 1),
                    "int8": ("b", 1),
                    "ushort": ("H", 2),
                    "uint16": ("H", 2),
                    "short": ("h", 2),
                    "int16": ("h", 2),
                    "uint": ("I", 4),
                    "uint32": ("I", 4),
                    "int": ("i", 4),
                    "int32": ("i", 4),
                }
                record_size = sum(type_map.get(ptype, ("x", 1))[1] for ptype, _ in vertex_properties)
                if (
                    record_size > 0
                    and len(vertex_properties) >= 3
                    and vertex_properties[0][1] == "x"
                    and vertex_properties[1][1] == "y"
                    and vertex_properties[2][1] == "z"
                ):
                    x_type = type_map.get(vertex_properties[0][0], ("f", 4))[0]
                    y_type = type_map.get(vertex_properties[1][0], ("f", 4))[0]
                    z_type = type_map.get(vertex_properties[2][0], ("f", 4))[0]
                    xyz_fmt = f"<{x_type}{y_type}{z_type}"
                    xyz_size = struct.calcsize(xyz_fmt)
                    skip_size = record_size - xyz_size

                    while points_read < min(point_count, sample_limit):
                        xyz_bytes = f.read(xyz_size)
                        if len(xyz_bytes) < xyz_size:
                            break
                        x, y, z = struct.unpack(xyz_fmt, xyz_bytes)
                        if skip_size > 0:
                            f.seek(skip_size, 1)
                        min_x, max_x = min(min_x, x), max(max_x, x)
                        min_y, max_y = min(min_y, y), max(max_y, y)
                        min_z, max_z = min(min_z, z), max(max_z, z)
                        points_read += 1
    except Exception as exc:
        logger.debug("Failed computing density bounds on %s: %s", p, exc)

    if points_read > 0 and max_x > min_x and max_y > min_y and max_z > min_z:
        volume = (max_x - min_x) * (max_y - min_y) * (max_z - min_z)
        if volume > 1e-9:
            return round(point_count / volume, 4)

    return float(point_count)


def export_sparse_points_ply(
    sparse_source: Path | str,
    dest_path: Path | str,
) -> Optional[Path]:
    """Preserve or convert sparse feature points to `points3D.ply`.

    Handles:
        1. Direct PLY files (`points3D.ply`, `sfm.ply`, etc.)
        2. Directory containing `points3D.ply` or `0/points3D.ply`
        3. Directory containing COLMAP `points3D.txt` or `0/points3D.txt`
        4. Directory containing COLMAP `points3D.bin` or `0/points3D.bin`

    Args:
        sparse_source: Path to sparse points file or directory.
        dest_path: Destination path where `points3D.ply` should be saved.

    Returns:
        Resolved Path to destination PLY if successful, else None.
    """
    src = Path(sparse_source).resolve()
    dest = Path(dest_path).resolve()
    ensure_directory(dest.parent)

    # 1. Direct file copy
    if src.is_file():
        if src.suffix.lower() == ".ply":
            shutil.copy2(src, dest)
            return dest
        if src.name.lower() in {"points3d.txt", "points.txt"}:
            return _convert_points3d_txt_to_ply(src, dest)
        if src.name.lower() in {"points3d.bin", "points.bin"}:
            return _convert_points3d_bin_to_ply(src, dest)

    # 2. Directory search
    if src.is_dir():
        candidates = [
            src / "points3D.ply",
            src / "0" / "points3D.ply",
            src / "sparse_points.ply",
            src / "points3D.txt",
            src / "0" / "points3D.txt",
            src / "points3D.bin",
            src / "0" / "points3D.bin",
        ]
        for c in candidates:
            if c.is_file():
                return export_sparse_points_ply(c, dest)

    return None


def _convert_points3d_txt_to_ply(txt_path: Path, dest_ply: Path) -> Path:
    """Convert COLMAP points3D.txt into standard PLY format."""
    points: list[tuple[float, float, float, int, int, int]] = []
    with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            if len(parts) >= 7:
                try:
                    x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                    r, g, b = int(parts[4]), int(parts[5]), int(parts[6])
                    points.append((x, y, z, r, g, b))
                except ValueError:
                    continue

    with open(dest_ply, "w", encoding="utf-8") as f:
        f.write("ply\n")
        f.write("format ascii 1.0\n")
        f.write(f"element vertex {len(points)}\n")
        f.write("property float x\n")
        f.write("property float y\n")
        f.write("property float z\n")
        f.write("property uchar red\n")
        f.write("property uchar green\n")
        f.write("property uchar blue\n")
        f.write("end_header\n")
        for x, y, z, r, g, b in points:
            f.write(f"{x:.6f} {y:.6f} {z:.6f} {r} {g} {b}\n")

    return dest_ply


def _convert_points3d_bin_to_ply(bin_path: Path, dest_ply: Path) -> Path:
    """Convert COLMAP points3D.bin into standard PLY format."""
    points: list[tuple[float, float, float, int, int, int]] = []
    try:
        with open(bin_path, "rb") as f:
            num_points_bytes = f.read(8)
            if len(num_points_bytes) == 8:
                num_points = struct.unpack("<Q", num_points_bytes)[0]
                for _ in range(num_points):
                    f.read(8)  # point3D_id
                    xyz_bytes = f.read(24)
                    rgb_bytes = f.read(3)
                    f.read(8)  # error
                    track_len_bytes = f.read(8)
                    if len(xyz_bytes) < 24 or len(rgb_bytes) < 3 or len(track_len_bytes) < 8:
                        break
                    x, y, z = struct.unpack("<3d", xyz_bytes)
                    r, g, b = struct.unpack("<3B", rgb_bytes)
                    track_len = struct.unpack("<Q", track_len_bytes)[0]
                    f.seek(track_len * 8, 1)  # skip track entries
                    points.append((x, y, z, r, g, b))
    except Exception as exc:
        logger.debug("Error parsing points3D.bin: %s", exc)

    with open(dest_ply, "w", encoding="utf-8") as f:
        f.write("ply\n")
        f.write("format ascii 1.0\n")
        f.write(f"element vertex {len(points)}\n")
        f.write("property float x\n")
        f.write("property float y\n")
        f.write("property float z\n")
        f.write("property uchar red\n")
        f.write("property uchar green\n")
        f.write("property uchar blue\n")
        f.write("end_header\n")
        for x, y, z, r, g, b in points:
            f.write(f"{x:.6f} {y:.6f} {z:.6f} {r} {g} {b}\n")

    return dest_ply


def export_reconstruction_checkpoints(
    run_name: str,
    output_root: Path | str,
    sparse_source: Path | str | None = None,
    dense_source: Path | str | None = None,
    mesh_source: Path | str | None = None,
    floor_removed_source: Path | str | None = None,
    base_capped_source: Path | str | None = None,
    min_points_threshold: int = 50000,
) -> ReconstructionCheckpointsArtifact:
    """Preserve and export intermediate reconstruction artifacts to disk.

    Output layout:
        <output_root>/reconstructions/<run_name>/
            01_sparse/points3D.ply
            02_dense/fused.ply
            03_raw_mesh/meshed-poisson.ply
            04_floor_removed.ply (optional)
            05_base_capped.ply (optional)

    Performs point cloud diagnostic on `02_dense/fused.ply`:
        - Reads vertex count of fused.ply.
        - Computes spatial density.
        - If points < min_points_threshold (50,000), logs a high-severity warning
          that parallax/coverage was insufficient during capture.

    Args:
        run_name: Unique run or pipeline execution name.
        output_root: Base output directory (typically `outputs`).
        sparse_source: Path to sparse SfM model directory or points3D file.
        dense_source: Path to dense fused point cloud (.ply).
        mesh_source: Path to raw Poisson mesh (.ply).
        floor_removed_source: Path to floor-removed intermediate mesh (.ply).
        base_capped_source: Path to base-capped intermediate mesh (.ply).
        min_points_threshold: Minimum expected point count (default: 50,000).

    Returns:
        ReconstructionCheckpointsArtifact with resolved checkpoint paths and metrics.
    """
    base_reconstructions = ensure_directory(Path(output_root) / "reconstructions" / run_name)

    # 1. 01_sparse/points3D.ply
    sparse_target_dir = ensure_directory(base_reconstructions / "01_sparse")
    sparse_target_file = sparse_target_dir / "points3D.ply"
    exported_sparse: Optional[Path] = None

    if sparse_source is not None:
        exported_sparse = export_sparse_points_ply(sparse_source, sparse_target_file)

    # 2. 02_dense/fused.ply
    dense_target_dir = ensure_directory(base_reconstructions / "02_dense")
    dense_target_file = dense_target_dir / "fused.ply"
    exported_dense: Optional[Path] = None

    if dense_source is not None:
        src_dense = Path(dense_source).resolve()
        if src_dense.is_file():
            shutil.copy2(src_dense, dense_target_file)
            exported_dense = dense_target_file
        elif src_dense.is_dir() and (src_dense / "fused.ply").is_file():
            shutil.copy2(src_dense / "fused.ply", dense_target_file)
            exported_dense = dense_target_file

    # 3. 03_raw_mesh/meshed-poisson.ply
    mesh_target_dir = ensure_directory(base_reconstructions / "03_raw_mesh")
    mesh_target_file = mesh_target_dir / "meshed-poisson.ply"
    exported_mesh: Optional[Path] = None

    if mesh_source is not None:
        src_mesh = Path(mesh_source).resolve()
        if src_mesh.is_file():
            shutil.copy2(src_mesh, mesh_target_file)
            exported_mesh = mesh_target_file
        elif src_mesh.is_dir() and (src_mesh / "meshed-poisson.ply").is_file():
            shutil.copy2(src_mesh / "meshed-poisson.ply", mesh_target_file)
            exported_mesh = mesh_target_file

    # 4. 04_floor_removed.ply (optional)
    floor_target_file = base_reconstructions / "04_floor_removed.ply"
    exported_floor: Optional[Path] = None
    if floor_removed_source is not None:
        src_floor = Path(floor_removed_source).resolve()
        if src_floor.is_file():
            shutil.copy2(src_floor, floor_target_file)
            exported_floor = floor_target_file

    # 5. 05_base_capped.ply (optional)
    capped_target_file = base_reconstructions / "05_base_capped.ply"
    exported_capped: Optional[Path] = None
    if base_capped_source is not None:
        src_capped = Path(base_capped_source).resolve()
        if src_capped.is_file():
            shutil.copy2(src_capped, capped_target_file)
            exported_capped = capped_target_file

    # 6. Point Cloud Diagnostic on fused.ply
    point_count = 0
    point_density = 0.0
    insufficient_coverage_warning = False

    active_fused = exported_dense if exported_dense else (dense_target_file if dense_target_file.is_file() else None)
    if active_fused is not None and active_fused.is_file():
        point_count = read_ply_vertex_count(active_fused)
        point_density = compute_ply_density(active_fused, point_count)

        logger.info(
            "Point cloud diagnostic for '%s': total_points=%d, density=%.2f pts/unit³",
            run_name,
            point_count,
            point_density,
        )

        if point_count < min_points_threshold:
            insufficient_coverage_warning = True
            logger.warning(
                "HIGH SEVERITY WARNING: Fused point cloud has insufficient points (%d < %d threshold). "
                "Parallax or coverage was insufficient during capture, risking incomplete surface reconstruction.",
                point_count,
                min_points_threshold,
            )

    return ReconstructionCheckpointsArtifact(
        stage_name="reconstruction_checkpoints",
        run_name=run_name,
        reconstruction_dir=base_reconstructions.resolve(),
        sparse_points_path=exported_sparse.resolve() if exported_sparse else None,
        dense_point_cloud_path=exported_dense.resolve() if exported_dense else None,
        raw_mesh_path=exported_mesh.resolve() if exported_mesh else None,
        floor_removed_mesh_path=exported_floor.resolve() if exported_floor else None,
        base_capped_mesh_path=exported_capped.resolve() if exported_capped else None,
        point_count=point_count,
        point_density=point_density,
        insufficient_coverage_warning=insufficient_coverage_warning,
        min_points_threshold=min_points_threshold,
        metadata={
            "sparse_exported": exported_sparse is not None,
            "dense_exported": exported_dense is not None,
            "mesh_exported": exported_mesh is not None,
            "floor_removed_exported": exported_floor is not None,
            "base_capped_exported": exported_capped is not None,
        },
    )
