"""Canonical coordinate frame normalization via RANSAC support plane alignment."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Optional, Tuple, Union

import numpy as np
import trimesh

logger = logging.getLogger(__name__)


def read_ply_with_normals(path: Path | str) -> tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]:
    """Read binary little-endian or ASCII PLY file returning (vertices, normals, colors).

    Args:
        path: Path to .ply point cloud file.

    Returns:
        Tuple of:
            - vertices: (N, 3) float64 array of 3D coordinates.
            - normals: (N, 3) float64 array of unit normal vectors (nx, ny, nz).
            - colors: (N, 3) uint8 array of RGB colors or None.
    """
    p = Path(path).resolve()
    with open(p, "rb") as f:
        header_lines = []
        while True:
            line = f.readline()
            if not line:
                break
            line_str = line.decode("ascii", errors="replace").strip()
            header_lines.append(line_str)
            if line_str == "end_header":
                break

    num_vertices = 0
    properties: list[tuple[str, str]] = []
    is_binary = False
    for line in header_lines:
        if line.startswith("format binary_little_endian"):
            is_binary = True
        elif line.startswith("element vertex"):
            parts = line.split()
            if len(parts) >= 3:
                num_vertices = int(parts[2])
        elif line.startswith("property"):
            parts = line.split()
            if len(parts) >= 3:
                properties.append((parts[2], parts[1]))  # (name, type)

    type_map = {
        "float": "<f4",
        "float32": "<f4",
        "double": "<f8",
        "float64": "<f8",
        "uchar": "u1",
        "uint8": "u1",
        "int": "<i4",
        "int32": "<i4",
    }
    has_xyz = all(name in [prop[0] for prop in properties] for name in ["x", "y", "z"])
    has_normals = all(name in [prop[0] for prop in properties] for name in ["nx", "ny", "nz"])
    has_colors = all(name in [prop[0] for prop in properties] for name in ["red", "green", "blue"])

    if is_binary and has_xyz and num_vertices > 0:
        numpy_fields = []
        for name, ptype in properties:
            numpy_fields.append((name, type_map.get(ptype, "<f4")))
        dtype = np.dtype(numpy_fields)
        with open(p, "rb") as f:
            while True:
                l = f.readline()
                if l.strip() == b"end_header":
                    break
            data = np.fromfile(f, dtype=dtype, count=num_vertices)

        pts = np.column_stack([data["x"], data["y"], data["z"]]).astype(np.float64)
        if has_normals:
            norms = np.column_stack([data["nx"], data["ny"], data["nz"]]).astype(np.float64)
        else:
            norms = np.zeros_like(pts)
        if has_colors:
            colors = np.column_stack([data["red"], data["green"], data["blue"]]).astype(np.uint8)
        else:
            colors = None
        return pts, norms, colors
    else:
        loaded = trimesh.load(str(p))
        pts = np.asarray(loaded.vertices, dtype=np.float64)
        norms = getattr(loaded, "vertex_normals", None)
        if norms is None or len(norms) != len(pts):
            norms = np.zeros_like(pts)
        else:
            norms = np.asarray(norms, dtype=np.float64)
        colors = getattr(loaded.visual, "vertex_colors", None)
        if colors is not None and len(colors) == len(pts):
            colors = np.asarray(colors[:, :3], dtype=np.uint8)
        else:
            colors = None
        return pts, norms, colors


def write_ply_with_normals(
    path: Path | str,
    vertices: np.ndarray,
    normals: np.ndarray,
    colors: Optional[np.ndarray] = None,
) -> Path:
    """Write binary little-endian PLY preserving vertices, vertex normals, and optional colors.

    Args:
        path: Target file path.
        vertices: (N, 3) float array of 3D coordinates.
        normals: (N, 3) float array of unit normal vectors.
        colors: Optional (N, 3) uint8 array of RGB colors.

    Returns:
        Resolved Path to written file.
    """
    p = Path(path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    n_pts = len(vertices)
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"element vertex {n_pts}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "property float nx\n"
        "property float ny\n"
        "property float nz\n"
        "property uchar red\n"
        "property uchar green\n"
        "property uchar blue\n"
        "end_header\n"
    ).encode("ascii")

    data = np.empty(
        n_pts,
        dtype=[
            ("x", "<f4"),
            ("y", "<f4"),
            ("z", "<f4"),
            ("nx", "<f4"),
            ("ny", "<f4"),
            ("nz", "<f4"),
            ("red", "u1"),
            ("green", "u1"),
            ("blue", "u1"),
        ],
    )
    data["x"] = vertices[:, 0].astype(np.float32)
    data["y"] = vertices[:, 1].astype(np.float32)
    data["z"] = vertices[:, 2].astype(np.float32)
    data["nx"] = normals[:, 0].astype(np.float32)
    data["ny"] = normals[:, 1].astype(np.float32)
    data["nz"] = normals[:, 2].astype(np.float32)
    if colors is not None and len(colors) == n_pts:
        data["red"] = colors[:, 0].astype(np.uint8)
        data["green"] = colors[:, 1].astype(np.uint8)
        data["blue"] = colors[:, 2].astype(np.uint8)
    else:
        data["red"] = 200
        data["green"] = 200
        data["blue"] = 200

    with open(p, "wb") as f:
        f.write(header)
        data.tofile(f)
    return p


def extract_colmap_camera_centers(sparse_model_dir: Path | str) -> Optional[np.ndarray]:
    """Extract camera centers in world coordinates from COLMAP sparse model.

    For each registered image, camera optical center in world frame is C = -R^T · t.
    """
    try:
        from loom.scaling.aruco import load_colmap_model

        _, images = load_colmap_model(sparse_model_dir)
        if not images:
            return None
        centers = []
        for img in images.values():
            c = -img.R.T @ img.tvec
            centers.append(c)
        return np.array(centers, dtype=np.float64)
    except Exception:
        return None


@dataclass(frozen=True)
class PlaneModel:
    """Parametric representation of a 3D plane: n · x + d = 0."""

    normal: np.ndarray  # Unit normal vector (3,)
    d: float  # Distance scalar
    inlier_indices: np.ndarray  # Indices of inlier points


@dataclass(frozen=True)
class AlignmentResult:
    """Result of canonical coordinate alignment."""

    rotation_matrix: np.ndarray  # 3x3 rotation matrix R
    translation_vector: np.ndarray  # 3D translation vector t
    transform_4x4: np.ndarray  # 4x4 homogeneous transformation matrix
    support_plane: PlaneModel  # Detected support plane parameters
    aligned_points: np.ndarray  # Normalized N x 3 point array
    inlier_count: int = 0
    transformed_cloud_path: Optional[Path] = None
    aligned_normals: Optional[np.ndarray] = None


class CoordinateNormalizer:
    """Normalizes arbitrary reconstruction frames to gravity-aligned canonical space."""

    def __init__(
        self,
        distance_threshold: Optional[float] = None,
        max_iterations: int = 1500,
        normal_up_target: Optional[np.ndarray] = None,
    ):
        self.distance_threshold = distance_threshold
        self.max_iterations = max_iterations
        target = normal_up_target if normal_up_target is not None else np.array([0.0, 0.0, 1.0])
        norm = np.linalg.norm(target)
        self.normal_up_target = target / norm if norm > 1e-8 else np.array([0.0, 0.0, 1.0])

    def fit_support_plane_ransac(
        self,
        points: np.ndarray,
        threshold: Optional[float] = None,
        camera_centers: Optional[np.ndarray] = None,
    ) -> PlaneModel:
        """Fit dominant support plane using vectorized RANSAC across the scene."""
        n_points = len(points)
        if n_points < 3:
            raise ValueError(f"Need at least 3 points to fit a plane, got {n_points}")

        if threshold is None:
            bbox_diag = float(np.linalg.norm(points.max(axis=0) - points.min(axis=0)))
            threshold = 0.012 * bbox_diag if bbox_diag > 0 else 0.015

        rng = np.random.default_rng(42)

        # Sample up to 60,000 points for candidate RANSAC evaluation
        if n_points > 60000:
            sample_indices = rng.choice(n_points, size=60000, replace=False)
            eval_pts = points[sample_indices]
        else:
            sample_indices = np.arange(n_points)
            eval_pts = points

        n_eval = len(eval_pts)
        best_inliers_eval = np.array([], dtype=np.int64)
        best_normal = np.array([0.0, 0.0, 1.0])
        best_d = 0.0

        for _ in range(self.max_iterations):
            idx = rng.choice(n_eval, size=3, replace=False)
            p1, p2, p3 = eval_pts[idx]

            v1 = p2 - p1
            v2 = p3 - p1
            normal = np.cross(v1, v2)
            norm = float(np.linalg.norm(normal))
            if norm < 1e-8:
                continue

            normal = normal / norm
            d = -float(np.dot(normal, p1))

            distances = np.abs(np.dot(eval_pts, normal) + d)
            inliers = np.where(distances <= threshold)[0]

            if len(inliers) > len(best_inliers_eval):
                best_inliers_eval = inliers
                best_normal = normal
                best_d = d

        if len(best_inliers_eval) < 3:
            raise RuntimeError("RANSAC failed to isolate a valid support plane.")

        # Upward Gravity Polarity Check: Normal must point UP toward camera trajectory or non-plane object mass
        if camera_centers is not None and len(camera_centers) > 0:
            c_cam = np.mean(camera_centers, axis=0)
            p0 = -best_d * best_normal
            if np.dot(best_normal, c_cam - p0) < 0:
                best_normal = -best_normal
                best_d = -best_d
        else:
            non_inliers_eval = eval_pts[np.setdiff1d(np.arange(n_eval), best_inliers_eval, assume_unique=True)]
            if len(non_inliers_eval) > 0:
                signed_dists = np.dot(non_inliers_eval, best_normal) + best_d
                if np.median(signed_dists) < 0:
                    best_normal = -best_normal
                    best_d = -best_d

        # Map inliers back to full points array
        if n_points > 60000:
            full_distances = np.abs(np.dot(points, best_normal) + best_d)
            best_inliers_full = np.where(full_distances <= threshold)[0]
        else:
            best_inliers_full = best_inliers_eval

        return PlaneModel(normal=best_normal, d=best_d, inlier_indices=best_inliers_full)

    def compute_alignment_matrix(
        self,
        plane: PlaneModel,
        points: np.ndarray,
        center_elevated: bool = False,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Compute R and t aligning plane normal to target up vector and setting plane at Z=0."""
        n = plane.normal
        target = self.normal_up_target

        v = np.cross(n, target)
        s = float(np.linalg.norm(v))
        c = float(np.dot(n, target))

        if s < 1e-8:
            if c > 0:
                R = np.eye(3)
            else:
                # 180-degree rotation around an orthogonal axis in SO(3)
                ortho = np.array([1.0, 0.0, 0.0]) if abs(target[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
                axis = np.cross(target, ortho)
                axis = axis / np.linalg.norm(axis)
                R = 2.0 * np.outer(axis, axis) - np.eye(3)
        else:
            vx = np.array([
                [0.0, -v[2], v[1]],
                [v[2], 0.0, -v[0]],
                [-v[1], v[0], 0.0],
            ])
            R = np.eye(3) + vx + (vx @ vx) * ((1.0 - c) / (s**2))

        rotated_pts = points @ R.T
        plane_z = float(np.median(rotated_pts[plane.inlier_indices, 2]))
        if center_elevated:
            elevated_mask = rotated_pts[:, 2] > (plane_z + 0.015)
            if np.sum(elevated_mask) >= 10:
                xy_center = np.median(rotated_pts[elevated_mask, :2], axis=0)
            else:
                xy_center = np.median(rotated_pts[:, :2], axis=0)
        else:
            xy_center = rotated_pts[:, :2].mean(axis=0)

        t = np.array([-xy_center[0], -xy_center[1], -plane_z])

        T = np.eye(4)
        T[:3, :3] = R
        T[:3, 3] = t

        return R, t, T

    def normalize(
        self,
        geometry: Union[np.ndarray, trimesh.PointCloud, trimesh.Trimesh, Path, str],
        output_path: Optional[Path | str] = None,
        camera_centers: Optional[np.ndarray] = None,
        normals: Optional[np.ndarray] = None,
        center_elevated: bool = False,
    ) -> Tuple[Union[np.ndarray, trimesh.PointCloud, trimesh.Trimesh], AlignmentResult]:
        """Normalize geometry so support plane sits at Z=0 with normal [0, 0, 1]."""
        pts_normals = normals
        colors = None
        orig_path = None
        if isinstance(geometry, (str, Path)):
            orig_path = Path(geometry).resolve()
            if orig_path.suffix.lower() == ".ply":
                pts, loaded_norms, colors = read_ply_with_normals(orig_path)
                if pts_normals is None and np.any(loaded_norms != 0):
                    pts_normals = loaded_norms
                geometry = trimesh.PointCloud(vertices=pts, colors=colors)
            else:
                geometry = trimesh.load(str(orig_path))

        if isinstance(geometry, (trimesh.PointCloud, trimesh.Trimesh)):
            pts = np.asarray(geometry.vertices, dtype=np.float64)
            if pts_normals is None:
                v_norms = getattr(geometry, "vertex_normals", None)
                if v_norms is not None and len(v_norms) == len(pts):
                    pts_normals = np.asarray(v_norms, dtype=np.float64)
            if colors is None:
                v_cols = getattr(geometry.visual, "vertex_colors", None)
                if v_cols is not None and len(v_cols) == len(pts):
                    colors = np.asarray(v_cols[:, :3], dtype=np.uint8)
        else:
            pts = np.asarray(geometry, dtype=np.float64)

        plane = self.fit_support_plane_ransac(
            pts, threshold=self.distance_threshold, camera_centers=camera_centers
        )
        R, t, T = self.compute_alignment_matrix(plane, pts, center_elevated=center_elevated)

        aligned_pts = (pts @ R.T) + t
        aligned_norms: Optional[np.ndarray] = None
        if pts_normals is not None:
            rotated_norms = np.asarray(pts_normals, dtype=np.float64) @ R.T
            norm_lengths = np.linalg.norm(rotated_norms, axis=1, keepdims=True)
            nonzero = norm_lengths > 1e-12
            aligned_norms = np.where(nonzero, rotated_norms / np.where(nonzero, norm_lengths, 1.0), rotated_norms)

        if isinstance(geometry, trimesh.Trimesh):
            aligned_geom = geometry.copy()
            aligned_geom.apply_transform(T)
        elif isinstance(geometry, trimesh.PointCloud):
            aligned_geom = trimesh.PointCloud(
                vertices=aligned_pts,
                colors=colors,
            )
        else:
            aligned_geom = aligned_pts

        out_file_path: Optional[Path] = None
        if output_path is not None:
            out_file_path = Path(output_path).resolve()
            out_file_path.parent.mkdir(parents=True, exist_ok=True)
            if aligned_norms is not None and len(aligned_norms) == len(aligned_pts):
                write_ply_with_normals(out_file_path, aligned_pts, aligned_norms, colors)
            elif isinstance(aligned_geom, (trimesh.Trimesh, trimesh.PointCloud)):
                aligned_geom.export(str(out_file_path))

        result = AlignmentResult(
            rotation_matrix=R,
            translation_vector=t,
            transform_4x4=T,
            support_plane=plane,
            aligned_points=aligned_pts,
            inlier_count=len(plane.inlier_indices),
            transformed_cloud_path=out_file_path,
            aligned_normals=aligned_norms,
        )
        return aligned_geom, result

