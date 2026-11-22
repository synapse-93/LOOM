"""True multi-view visual-hull sparse point filtering and tight DBSCAN core framing."""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

import cv2
import numpy as np

from loom.scaling.aruco import ColmapCamera, ColmapImage, load_colmap_model
from loom.utils.paths import ensure_directory

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VisualHullConfig:
    """Parameters governing multi-view visual-hull intersection and DBSCAN core clustering."""

    min_visible_views: int = 8
    min_visible_fraction: float = 0.20
    fallback_min_visible_views: int = 5
    min_fg_ratio: float = 0.70
    relax_ratios: tuple[float, ...] = (0.55, 0.40)
    min_surviving_points: int = 500
    dbscan_eps_scene_ratio: float = 0.08
    dbscan_min_points: int = 15
    dbscan_min_cluster_size: int = 200
    mad_multiplier: float = 2.0
    radius_percentile: float = 95.0
    min_mask_coverage: float = 0.02
    max_mask_coverage: float = 0.95


@dataclass(frozen=True)
class VisualHullResult:
    """Typed output contract from VisualHullFilter."""

    total_sparse_points: int
    foreground_points: int
    hit_ratio_threshold_used: float
    object_center: tuple[float, float, float]
    object_radius: float
    scene_radius: float
    filtered_ply_path: Path
    points_xyz: np.ndarray
    points_rgb: np.ndarray

    def to_manifest_dict(self) -> dict[str, Any]:
        return {
            "total_sparse_points": int(self.total_sparse_points),
            "foreground_points": int(self.foreground_points),
            "hit_ratio_threshold_used": float(self.hit_ratio_threshold_used),
            "object_center": [round(float(c), 6) for c in self.object_center],
            "object_radius": round(float(self.object_radius), 6),
            "scene_radius": round(float(self.scene_radius), 6),
            "filtered_ply_path": str(self.filtered_ply_path),
        }


def compute_camera_lookat_center(
    cam_centers: np.ndarray,
    cam_forwards: np.ndarray,
) -> np.ndarray:
    """Compute least-squares closest 3D point to all valid camera optical axes."""
    origins = np.asarray(cam_centers, dtype=np.float64)
    dirs = np.asarray(cam_forwards, dtype=np.float64)
    if len(origins) == 0:
        return np.zeros(3, dtype=np.float64)
    if len(origins) == 1:
        return origins[0] + dirs[0]

    norms = np.linalg.norm(dirs, axis=1, keepdims=True)
    dirs = dirs / np.maximum(norms, 1e-12)

    A = np.zeros((3, 3), dtype=np.float64)
    b = np.zeros(3, dtype=np.float64)
    eye3 = np.eye(3, dtype=np.float64)
    for o, d in zip(origins, dirs):
        proj = eye3 - np.outer(d, d)
        A += proj
        b += proj @ o

    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    if not np.all(np.isfinite(sol)):
        return np.median(origins, axis=0)
    return sol.astype(np.float64)


def _read_points3d_bin(path: Path) -> tuple[np.ndarray, np.ndarray]:
    xyz_list: list[tuple[float, float, float]] = []
    rgb_list: list[tuple[int, int, int]] = []
    with open(path, "rb") as f:
        num_points = struct.unpack("<Q", f.read(8))[0]
        for _ in range(num_points):
            _pid = struct.unpack("<Q", f.read(8))[0]
            x, y, z = struct.unpack("<3d", f.read(24))
            r, g, b = struct.unpack("<3B", f.read(3))
            _err = struct.unpack("<d", f.read(8))[0]
            track_len = struct.unpack("<Q", f.read(8))[0]
            if track_len > 0:
                f.seek(track_len * 8, 1)
            xyz_list.append((x, y, z))
            rgb_list.append((r, g, b))
    if not xyz_list:
        return np.zeros((0, 3), dtype=np.float64), np.zeros((0, 3), dtype=np.uint8)
    return np.asarray(xyz_list, dtype=np.float64), np.asarray(rgb_list, dtype=np.uint8)


def _read_points3d_txt(path: Path) -> tuple[np.ndarray, np.ndarray]:
    xyz_list: list[tuple[float, float, float]] = []
    rgb_list: list[tuple[int, int, int]] = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            if len(parts) >= 7:
                xyz_list.append((float(parts[1]), float(parts[2]), float(parts[3])))
                rgb_list.append((int(parts[4]), int(parts[5]), int(parts[6])))
    if not xyz_list:
        return np.zeros((0, 3), dtype=np.float64), np.zeros((0, 3), dtype=np.uint8)
    return np.asarray(xyz_list, dtype=np.float64), np.asarray(rgb_list, dtype=np.uint8)


def _load_undistorted_points3d(undistorted_sparse_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    """Load 3D points strictly from an undistorted COLMAP sparse directory (dense/sparse/)."""
    d = undistorted_sparse_dir.resolve()
    if (d / "points3D.bin").is_file():
        return _read_points3d_bin(d / "points3D.bin")
    if (d / "points3D.txt").is_file():
        return _read_points3d_txt(d / "points3D.txt")
    raise FileNotFoundError(
        f"Expected undistorted points3D.bin or points3D.txt directly in '{d}' (dense/sparse/)."
    )


def write_colored_ply(path: Path | str, points_xyz: np.ndarray, points_rgb: np.ndarray) -> Path:
    """Write binary little-endian RGB point cloud PLY for MeshLab visual inspection."""
    dest = Path(path).resolve()
    ensure_directory(dest.parent)

    pts = np.asarray(points_xyz, dtype=np.float32)
    rgb = np.asarray(points_rgb, dtype=np.uint8)
    n = len(pts)

    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"element vertex {n}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "property uchar red\n"
        "property uchar green\n"
        "property uchar blue\n"
        "end_header\n"
    ).encode("ascii")

    rec = np.empty(
        n,
        dtype=[
            ("x", "<f4"),
            ("y", "<f4"),
            ("z", "<f4"),
            ("red", "u1"),
            ("green", "u1"),
            ("blue", "u1"),
        ],
    )
    if n > 0:
        rec["x"] = pts[:, 0]
        rec["y"] = pts[:, 1]
        rec["z"] = pts[:, 2]
        if len(rgb) == n:
            rec["red"] = rgb[:, 0]
            rec["green"] = rgb[:, 1]
            rec["blue"] = rgb[:, 2]
        else:
            rec["red"] = 200
            rec["green"] = 200
            rec["blue"] = 200

    with open(dest, "wb") as f:
        f.write(header)
        rec.tofile(f)
    return dest


def read_colored_ply(path: Path | str) -> tuple[np.ndarray, np.ndarray]:
    """Read binary little-endian RGB PLY written by ``write_colored_ply`` (fallback via trimesh)."""
    p = Path(path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"PLY file not found: {p}")

    with open(p, "rb") as f:
        header_lines: list[str] = []
        while True:
            raw = f.readline()
            if not raw:
                break
            line = raw.decode("ascii", errors="replace").strip()
            header_lines.append(line)
            if line == "end_header":
                break
        data_offset = f.tell()

    is_binary = any(l.startswith("format binary_little_endian") for l in header_lines)
    num_vertices = 0
    props: list[tuple[str, str]] = []
    for l in header_lines:
        if l.startswith("element vertex"):
            num_vertices = int(l.split()[2])
        elif l.startswith("property"):
            parts = l.split()
            if len(parts) >= 3:
                props.append((parts[2], parts[1]))

    type_map = {
        "float": "<f4",
        "float32": "<f4",
        "double": "<f8",
        "float64": "<f8",
        "uchar": "u1",
        "uint8": "u1",
    }
    prop_names = {name for name, _ in props}
    if is_binary and {"x", "y", "z"}.issubset(prop_names):
        dtype = np.dtype([(name, type_map.get(t, "<f4")) for name, t in props])
        with open(p, "rb") as f:
            f.seek(data_offset)
            arr = np.fromfile(f, dtype=dtype, count=num_vertices)
        xyz = np.column_stack([arr["x"], arr["y"], arr["z"]]).astype(np.float64)
        if {"red", "green", "blue"}.issubset(prop_names):
            rgb = np.column_stack([arr["red"], arr["green"], arr["blue"]]).astype(np.uint8)
        else:
            rgb = np.full((len(xyz), 3), 200, dtype=np.uint8)
        return xyz, rgb

    import trimesh

    loaded = trimesh.load(str(p))
    xyz = np.asarray(loaded.vertices, dtype=np.float64)
    cols = getattr(getattr(loaded, "visual", None), "vertex_colors", None)
    if cols is not None and len(cols) == len(xyz):
        rgb = np.asarray(cols[:, :3], dtype=np.uint8)
    else:
        rgb = np.full((len(xyz), 3), 200, dtype=np.uint8)
    return xyz, rgb


class VisualHullFilter:
    """Isolates true foreground 3D points via multi-view undistorted silhouette intersection + DBSCAN core."""

    def __init__(self, config: Optional[VisualHullConfig] = None) -> None:
        self.config = config or VisualHullConfig()

    def _select_dbscan_core_cluster(
        self,
        fg_pts: np.ndarray,
        fg_rgb: np.ndarray,
        lookat_center: np.ndarray,
        scene_radius_est: float,
    ) -> tuple[np.ndarray, np.ndarray, str]:
        """Run Open3D DBSCAN and retain the largest dense cluster closest to camera-ray convergence."""
        import open3d as o3d

        eps = max(float(self.config.dbscan_eps_scene_ratio) * float(scene_radius_est), 1e-3)
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(fg_pts)
        labels = np.asarray(
            pcd.cluster_dbscan(
                eps=eps,
                min_points=int(self.config.dbscan_min_points),
                print_progress=False,
            )
        )

        unique_labels = [int(lbl) for lbl in np.unique(labels) if lbl >= 0]
        qualifying: list[tuple[int, int, float]] = []  # (label, size, dist_to_lookat)

        for lbl in unique_labels:
            idx = np.nonzero(labels == lbl)[0]
            size = int(len(idx))
            if size >= int(self.config.dbscan_min_cluster_size):
                c_med = np.median(fg_pts[idx], axis=0)
                dist = float(np.linalg.norm(c_med - lookat_center))
                qualifying.append((lbl, size, dist))

        if qualifying:
            # Prefer dense clusters closest to camera-ray convergence point:
            # among substantial clusters (>= 25% of largest cluster), pick the one closest to lookat_center;
            # tie-break by largest point count.
            max_size = max(item[1] for item in qualifying)
            substantial = [item for item in qualifying if item[1] >= max(int(self.config.dbscan_min_cluster_size), int(0.25 * max_size))]
            substantial.sort(key=lambda item: (item[2], -item[1]))
            win_lbl, win_size, win_dist = substantial[0]
            mask = labels == win_lbl
            logger.info(
                "[VISUAL_HULL] DBSCAN (eps=%.4f, min_pts=%d): %d qualifying clusters -> selected core cluster #%d (%d pts, dist_to_lookat=%.4f)",
                eps,
                int(self.config.dbscan_min_points),
                len(qualifying),
                win_lbl,
                win_size,
                win_dist,
            )
            return fg_pts[mask], fg_rgb[mask], "dbscan"

        # Fallback: median + 2.0 * MAD distance from foreground median
        med_center = np.median(fg_pts, axis=0)
        dists_raw = np.linalg.norm(fg_pts - med_center[None, :], axis=1)
        med_dist = float(np.median(dists_raw))
        mad = float(np.median(np.abs(dists_raw - med_dist)))
        if mad > 1e-9:
            inliers = dists_raw <= (med_dist + float(self.config.mad_multiplier) * mad)
            if int(np.count_nonzero(inliers)) >= 16:
                logger.info(
                    "[VISUAL_HULL] DBSCAN found no cluster >= %d pts; applied median + %.1f*MAD fallback (%d -> %d pts)",
                    int(self.config.dbscan_min_cluster_size),
                    float(self.config.mad_multiplier),
                    len(fg_pts),
                    int(np.count_nonzero(inliers)),
                )
                return fg_pts[inliers], fg_rgb[inliers], "mad_fallback"

        return fg_pts, fg_rgb, "unpruned"

    def run(
        self,
        undistorted_sparse_dir: Path | str,
        masks_dir: Path | str,
        output_ply_path: Path | str,
        *,
        valid_view_names: Optional[Sequence[str]] = None,
    ) -> VisualHullResult:
        """Intersect undistorted PINHOLE cameras with binary foreground masks + DBSCAN core."""
        sparse_root = Path(undistorted_sparse_dir).resolve()
        mask_root = Path(masks_dir).resolve()

        if not sparse_root.is_dir():
            raise FileNotFoundError(f"Undistorted sparse directory not found: {sparse_root}")
        if not mask_root.is_dir():
            raise FileNotFoundError(f"Masks directory not found: {mask_root}")

        cameras, images = load_colmap_model(sparse_root)
        if not images:
            raise RuntimeError(f"No registered images found in undistorted sparse model: {sparse_root}")

        for cam in cameras.values():
            if cam.model.upper() not in {"PINHOLE", "SIMPLE_PINHOLE"}:
                logger.warning(
                    "[VISUAL_HULL] Camera #%d in %s uses model '%s' (expected undistorted PINHOLE).",
                    cam.camera_id,
                    sparse_root,
                    cam.model,
                )

        points_xyz, points_rgb = _load_undistorted_points3d(sparse_root)
        total_sparse = len(points_xyz)
        if total_sparse == 0:
            raise RuntimeError(f"Undistorted sparse model contains 0 3D points: {sparse_root}")

        allowed_set = set(valid_view_names) if valid_view_names is not None else None

        loaded_views: list[tuple[ColmapCamera, ColmapImage, np.ndarray]] = []
        valid_cam_centers: list[np.ndarray] = []
        valid_cam_forwards: list[np.ndarray] = []
        all_cam_centers: list[np.ndarray] = []

        for img_id in sorted(images.keys()):
            img = images[img_id]
            cam = cameras.get(img.camera_id)
            if cam is None:
                continue
            c_world = -img.R.T @ img.tvec
            fwd_world = img.R[2, :]  # +Z optical axis in world frame
            all_cam_centers.append(c_world)

            if allowed_set is not None and img.name not in allowed_set:
                continue

            mask_path = mask_root / f"{Path(img.name).stem}.png"
            if not mask_path.is_file():
                continue

            mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
            if mask is None or mask.size == 0:
                continue

            if allowed_set is None:
                cov = float(np.mean(mask > 127))
                if cov < self.config.min_mask_coverage or cov > self.config.max_mask_coverage:
                    continue

            loaded_views.append((cam, img, mask))
            valid_cam_centers.append(c_world)
            valid_cam_forwards.append(fwd_world)

        if not loaded_views:
            raise RuntimeError("VisualHullFilter found zero valid (undistorted camera, mask) pairs.")

        cam_centers = np.asarray(all_cam_centers, dtype=np.float64)
        lookat_center = compute_camera_lookat_center(
            np.asarray(valid_cam_centers, dtype=np.float64),
            np.asarray(valid_cam_forwards, dtype=np.float64),
        )
        scene_radius_est = max(
            float(np.median(np.linalg.norm(cam_centers - lookat_center[None, :], axis=1))),
            0.1,
        )

        # Multi-view silhouette projection across all valid-mask undistorted cameras
        visible_count = np.zeros(total_sparse, dtype=np.int32)
        fg_hits = np.zeros(total_sparse, dtype=np.int32)

        for cam, img, mask in loaded_views:
            mh, mw = mask.shape[:2]
            K = cam.K.copy()
            if cam.width > 0 and cam.height > 0 and (mw != cam.width or mh != cam.height):
                K[0, 0] *= mw / float(cam.width)
                K[0, 2] *= mw / float(cam.width)
                K[1, 1] *= mh / float(cam.height)
                K[1, 2] *= mh / float(cam.height)

            cam_pts = (points_xyz @ img.R.T) + img.tvec[None, :]
            z = cam_pts[:, 2]
            front = z > 1e-4
            if not np.any(front):
                continue

            idx_front = np.nonzero(front)[0]
            x_f = cam_pts[idx_front, 0] / z[idx_front]
            y_f = cam_pts[idx_front, 1] / z[idx_front]

            u = (K[0, 0] * x_f + K[0, 2]).astype(np.int64)
            v = (K[1, 1] * y_f + K[1, 2]).astype(np.int64)

            in_bounds = (u >= 0) & (u < mw) & (v >= 0) & (v < mh)
            if not np.any(in_bounds):
                continue

            idx_in = idx_front[in_bounds]
            visible_count[idx_in] += 1
            hit = mask[v[in_bounds], u[in_bounds]] > 127
            if np.any(hit):
                fg_hits[idx_in[hit]] += 1

        # Raised visibility gate: max(8, int(0.20 * num_valid_views)), gracefully falling back to 5
        num_valid = len(loaded_views)
        strict_min_vis = min(
            max(int(self.config.min_visible_views), int(self.config.min_visible_fraction * num_valid)),
            num_valid,
        )
        fallback_min_vis = min(int(self.config.fallback_min_visible_views), num_valid)

        hit_ratio = np.where(
            visible_count > 0,
            fg_hits.astype(np.float64) / np.maximum(visible_count, 1),
            0.0,
        )

        thresholds = [
            float(self.config.min_fg_ratio),
            *[float(r) for r in self.config.relax_ratios if float(r) < float(self.config.min_fg_ratio)],
        ]

        keep = np.zeros(total_sparse, dtype=bool)
        used_threshold = thresholds[0]
        used_min_vis = strict_min_vis

        vis_schedule = [strict_min_vis]
        if fallback_min_vis < strict_min_vis:
            vis_schedule.append(fallback_min_vis)

        found_enough = False
        for min_vis in vis_schedule:
            for thresh in thresholds:
                cand = (visible_count >= min_vis) & (hit_ratio >= thresh)
                n_cand = int(np.count_nonzero(cand))
                keep = cand
                used_threshold = thresh
                used_min_vis = min_vis
                if n_cand >= int(self.config.min_surviving_points):
                    found_enough = True
                    break
            if found_enough:
                break

        if int(np.count_nonzero(keep)) == 0:
            raise RuntimeError(
                f"VisualHullFilter eliminated all {total_sparse} sparse points across {num_valid} valid views."
            )

        fg_pts = points_xyz[keep]
        fg_rgb = points_rgb[keep]

        # Open3D DBSCAN core cluster retention around camera-ray convergence point (MAD fallback)
        fg_pts, fg_rgb, cluster_mode = self._select_dbscan_core_cluster(
            fg_pts, fg_rgb, lookat_center, scene_radius_est
        )

        # Compute tight object bounding sphere strictly from core cluster
        object_center = np.median(fg_pts, axis=0)
        fg_dists = np.linalg.norm(fg_pts - object_center[None, :], axis=1)
        object_radius = max(float(np.percentile(fg_dists, self.config.radius_percentile)), 1e-3)
        scene_radius = (
            float(np.median(np.linalg.norm(cam_centers - object_center[None, :], axis=1)))
            if len(cam_centers) > 0
            else object_radius
        )

        ply_path = write_colored_ply(output_ply_path, fg_pts, fg_rgb)

        logger.info(
            "[VISUAL_HULL] %d -> %d core foreground points (vis>=%d, ratio>=%.2f, mode=%s across %d views) | "
            "object_radius=%.4f vs scene_radius=%.4f | saved=%s",
            total_sparse,
            len(fg_pts),
            used_min_vis,
            used_threshold,
            cluster_mode,
            num_valid,
            object_radius,
            scene_radius,
            ply_path,
        )

        return VisualHullResult(
            total_sparse_points=total_sparse,
            foreground_points=len(fg_pts),
            hit_ratio_threshold_used=used_threshold,
            object_center=(float(object_center[0]), float(object_center[1]), float(object_center[2])),
            object_radius=object_radius,
            scene_radius=scene_radius,
            filtered_ply_path=ply_path,
            points_xyz=fg_pts,
            points_rgb=fg_rgb,
        )
