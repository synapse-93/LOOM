"""ArUco fiducial marker detection interfaces and OpenCV implementation."""

from __future__ import annotations

from dataclasses import dataclass
import itertools
import math
from pathlib import Path
import struct
from typing import Optional, Sequence
import cv2
import numpy as np

from loom.scaling.exceptions import (
    ReferenceDetectionError,
    ScalingConfigError,
)
from loom.scaling.models import MarkerObservation, ReferenceMarker
from loom.utils.logging import get_logger

logger = get_logger("loom.scaling.aruco")

CAMERA_MODEL_PARAM_COUNTS: dict[str, int] = {
    "SIMPLE_PINHOLE": 3,
    "PINHOLE": 4,
    "SIMPLE_RADIAL": 4,
    "RADIAL": 5,
    "OPENCV": 8,
    "OPENCV_FISHEYE": 8,
    "FULL_OPENCV": 12,
    "FOV": 5,
    "SIMPLE_RADIAL_FISHEYE": 4,
    "RADIAL_FISHEYE": 5,
    "THIN_PRISM_FISHEYE": 12,
}
CAMERA_MODEL_IDS: dict[int, str] = {
    0: "SIMPLE_PINHOLE",
    1: "PINHOLE",
    2: "SIMPLE_RADIAL",
    3: "RADIAL",
    4: "OPENCV",
    5: "OPENCV_FISHEYE",
    6: "FULL_OPENCV",
    7: "FOV",
    8: "SIMPLE_RADIAL_FISHEYE",
    9: "RADIAL_FISHEYE",
    10: "THIN_PRISM_FISHEYE",
}


@dataclass
class ColmapCamera:
    """Parsed camera intrinsics from COLMAP reconstruction."""

    camera_id: int
    model: str
    width: int
    height: int
    params: np.ndarray
    K: np.ndarray  # 3x3 intrinsic matrix
    dist_coeffs: Optional[np.ndarray] = None


@dataclass
class ColmapImage:
    """Parsed camera pose from COLMAP reconstruction."""

    image_id: int
    qvec: np.ndarray  # (4,) [qw, qx, qy, qz]
    tvec: np.ndarray  # (3,) [tx, ty, tz]
    camera_id: int
    name: str
    R: np.ndarray  # (3, 3) rotation matrix (world to camera)


def qvec_to_rotmat(qvec: np.ndarray) -> np.ndarray:
    """Convert COLMAP quaternion [qw, qx, qy, qz] to 3x3 rotation matrix."""
    q = np.asarray(qvec, dtype=np.float64)
    norm = float(np.linalg.norm(q))
    if norm > 1e-12:
        q = q / norm
    w, x, y, z = float(q[0]), float(q[1]), float(q[2]), float(q[3])
    return np.array([
        [1.0 - 2.0 * (y**2 + z**2), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
        [2.0 * (x * y + z * w), 1.0 - 2.0 * (x**2 + z**2), 2.0 * (y * z - x * w)],
        [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x**2 + y**2)],
    ], dtype=np.float64)


def _build_intrinsics(
    model_name: str,
    params: np.ndarray,
) -> tuple[np.ndarray, Optional[np.ndarray]]:
    """Build 3x3 camera matrix K and distortion coefficients from COLMAP model and params."""
    p_arr = np.asarray(params, dtype=np.float64)
    model = model_name.upper()

    if model in ("SIMPLE_PINHOLE", "SIMPLE_RADIAL", "SIMPLE_RADIAL_FISHEYE"):
        f, cx, cy = float(p_arr[0]), float(p_arr[1]), float(p_arr[2])
        K = np.array([
            [f, 0.0, cx],
            [0.0, f, cy],
            [0.0, 0.0, 1.0],
        ], dtype=np.float64)
        dist = np.array([p_arr[3], 0.0, 0.0, 0.0], dtype=np.float64) if len(p_arr) > 3 else None
        return K, dist

    if model in ("RADIAL", "RADIAL_FISHEYE"):
        f, cx, cy = float(p_arr[0]), float(p_arr[1]), float(p_arr[2])
        K = np.array([
            [f, 0.0, cx],
            [0.0, f, cy],
            [0.0, 0.0, 1.0],
        ], dtype=np.float64)
        dist = np.array([p_arr[3], p_arr[4], 0.0, 0.0], dtype=np.float64) if len(p_arr) > 4 else None
        return K, dist

    if len(p_arr) >= 4:
        fx, fy, cx, cy = float(p_arr[0]), float(p_arr[1]), float(p_arr[2]), float(p_arr[3])
        K = np.array([
            [fx, 0.0, cx],
            [0.0, fy, cy],
            [0.0, 0.0, 1.0],
        ], dtype=np.float64)
        if len(p_arr) == 4:
            return K, None
        elif len(p_arr) >= 8:
            dist = np.array(p_arr[4:8], dtype=np.float64)
            return K, dist
        else:
            dist = np.array(p_arr[4:], dtype=np.float64)
            return K, dist

    f = float(p_arr[0]) if len(p_arr) > 0 else 1000.0
    K = np.array([
        [f, 0.0, 0.0],
        [0.0, f, 0.0],
        [0.0, 0.0, 1.0],
    ], dtype=np.float64)
    return K, None


def read_colmap_cameras_bin(path: Path | str) -> dict[int, ColmapCamera]:
    """Parse COLMAP cameras.bin file."""
    p = Path(path).resolve()
    cameras: dict[int, ColmapCamera] = {}
    with open(p, "rb") as f:
        num_cameras = struct.unpack("<Q", f.read(8))[0]
        for _ in range(num_cameras):
            camera_id, model_id = struct.unpack("<Ii", f.read(8))
            width, height = struct.unpack("<QQ", f.read(16))
            model_name = CAMERA_MODEL_IDS.get(model_id, "PINHOLE")
            num_params = CAMERA_MODEL_PARAM_COUNTS.get(model_name, 4)
            params = np.array(struct.unpack(f"<{num_params}d", f.read(8 * num_params)), dtype=np.float64)
            K, dist = _build_intrinsics(model_name, params)
            cameras[camera_id] = ColmapCamera(
                camera_id=camera_id,
                model=model_name,
                width=int(width),
                height=int(height),
                params=params,
                K=K,
                dist_coeffs=dist,
            )
    return cameras


def read_colmap_cameras_text(path: Path | str) -> dict[int, ColmapCamera]:
    """Parse COLMAP cameras.txt file."""
    p = Path(path).resolve()
    cameras: dict[int, ColmapCamera] = {}
    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            if len(parts) >= 5:
                camera_id = int(parts[0])
                model_name = parts[1].upper()
                width = int(parts[2])
                height = int(parts[3])
                params = np.array([float(x) for x in parts[4:]], dtype=np.float64)
                K, dist = _build_intrinsics(model_name, params)
                cameras[camera_id] = ColmapCamera(
                    camera_id=camera_id,
                    model=model_name,
                    width=width,
                    height=height,
                    params=params,
                    K=K,
                    dist_coeffs=dist,
                )
    return cameras


def read_colmap_images_bin(path: Path | str) -> dict[int, ColmapImage]:
    """Parse COLMAP images.bin file."""
    p = Path(path).resolve()
    images: dict[int, ColmapImage] = {}
    with open(p, "rb") as f:
        num_images = struct.unpack("<Q", f.read(8))[0]
        for _ in range(num_images):
            image_id = struct.unpack("<I", f.read(4))[0]
            qvec = np.array(struct.unpack("<4d", f.read(32)), dtype=np.float64)
            tvec = np.array(struct.unpack("<3d", f.read(24)), dtype=np.float64)
            camera_id = struct.unpack("<I", f.read(4))[0]
            name_chars: list[bytes] = []
            while True:
                ch = f.read(1)
                if not ch or ch == b"\x00":
                    break
                name_chars.append(ch)
            name = b"".join(name_chars).decode("utf-8", errors="ignore")
            num_points2D = struct.unpack("<Q", f.read(8))[0]
            if num_points2D > 0:
                f.seek(num_points2D * 24, 1)

            R = qvec_to_rotmat(qvec)
            images[image_id] = ColmapImage(
                image_id=image_id,
                qvec=qvec,
                tvec=tvec,
                camera_id=camera_id,
                name=name,
                R=R,
            )
    return images


def read_colmap_images_text(path: Path | str) -> dict[int, ColmapImage]:
    """Parse COLMAP images.txt file."""
    p = Path(path).resolve()
    images: dict[int, ColmapImage] = {}
    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        idx += 1
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 10:
            image_id = int(parts[0])
            qw, qx, qy, qz = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
            tx, ty, tz = float(parts[5]), float(parts[6]), float(parts[7])
            camera_id = int(parts[8])
            name = parts[9]
            qvec = np.array([qw, qx, qy, qz], dtype=np.float64)
            tvec = np.array([tx, ty, tz], dtype=np.float64)
            R = qvec_to_rotmat(qvec)
            images[image_id] = ColmapImage(
                image_id=image_id,
                qvec=qvec,
                tvec=tvec,
                camera_id=camera_id,
                name=name,
                R=R,
            )
            # Skip points2D line
            if idx < len(lines):
                idx += 1
    return images


def load_colmap_model(model_dir: Path | str) -> tuple[dict[int, ColmapCamera], dict[int, ColmapImage]]:
    """Load COLMAP camera models and registered image poses from a directory.

    Supports both binary (.bin) and text (.txt) formats, searching directly in model_dir
    or within subfolder model_dir / '0'.
    """
    p = Path(model_dir).resolve()
    candidates = [p, p / "0"]

    cameras_path: Optional[Path] = None
    images_path: Optional[Path] = None

    for cand in candidates:
        if (cand / "cameras.bin").is_file():
            cameras_path = cand / "cameras.bin"
            break
        elif (cand / "cameras.txt").is_file():
            cameras_path = cand / "cameras.txt"
            break

    for cand in candidates:
        if (cand / "images.bin").is_file():
            images_path = cand / "images.bin"
            break
        elif (cand / "images.txt").is_file():
            images_path = cand / "images.txt"
            break

    if cameras_path is None or images_path is None:
        raise FileNotFoundError(
            f"COLMAP cameras and images files (cameras.bin/.txt, images.bin/.txt) not found in {p}"
        )

    if cameras_path.suffix == ".bin":
        cameras = read_colmap_cameras_bin(cameras_path)
    else:
        cameras = read_colmap_cameras_text(cameras_path)

    if images_path.suffix == ".bin":
        images = read_colmap_images_bin(images_path)
    else:
        images = read_colmap_images_text(images_path)

    return cameras, images


def triangulate_multiview_point(
    proj_matrices: Sequence[np.ndarray],
    points_2d: Sequence[tuple[float, float] | np.ndarray],
    max_reproj_error_px: float = 2.0,
) -> tuple[Optional[np.ndarray], float, list[int]]:
    """Triangulate a 3D point from multiple 2D camera observations with outlier rejection.

    Uses DLT (Direct Linear Transform) via SVD. For > 2 views, runs RANSAC pair search
    to reject observations whose reprojection error exceeds max_reproj_error_px.

    Args:
        proj_matrices: List of 3x4 projection matrices P_i = K_i @ [R_i | t_i].
        points_2d: List of observed 2D pixel coordinates (u_i, v_i).
        max_reproj_error_px: Threshold in pixels above which observations are rejected (default: 2.0).

    Returns:
        Tuple of (point_3d, mean_reprojection_error, inlier_indices).
        If triangulation fails or fewer than 2 inliers exist, returns (None, inf, []).
    """
    n_views = len(points_2d)
    if n_views < 2:
        return None, float("inf"), []

    def _triangulate_indices(indices: Sequence[int]) -> Optional[np.ndarray]:
        A = []
        for idx in indices:
            p = proj_matrices[idx]
            u, v = float(points_2d[idx][0]), float(points_2d[idx][1])
            A.append(u * p[2] - p[0])
            A.append(v * p[2] - p[1])
        A_arr = np.asarray(A, dtype=np.float64)
        _, _, vt = np.linalg.svd(A_arr)
        x_hom = vt[-1]
        if abs(x_hom[3]) < 1e-12:
            return None
        return x_hom[:3] / x_hom[3]

    def _compute_reproj_errors(x_3d: np.ndarray) -> list[float]:
        errors = []
        x_hom = np.append(x_3d, 1.0)
        for p, pt_2d in zip(proj_matrices, points_2d):
            proj = p @ x_hom
            if proj[2] <= 1e-6:
                errors.append(float("inf"))
            else:
                u_pred = proj[0] / proj[2]
                v_pred = proj[1] / proj[2]
                err = math.hypot(u_pred - float(pt_2d[0]), v_pred - float(pt_2d[1]))
                errors.append(err)
        return errors

    # If only 2 views, direct triangulation
    if n_views == 2:
        x_init = _triangulate_indices([0, 1])
        if x_init is None:
            return None, float("inf"), []
        errs = _compute_reproj_errors(x_init)
        if all(e <= max_reproj_error_px for e in errs):
            return x_init, float(np.mean(errs)), [0, 1]
        return None, float("inf"), []

    # If > 2 views: RANSAC pair search
    best_inliers: list[int] = []
    best_x: Optional[np.ndarray] = None
    best_err: float = float("inf")

    pairs = list(itertools.combinations(range(n_views), 2))
    if len(pairs) > 100:
        rng = np.random.default_rng(42)
        sampled_indices = rng.choice(len(pairs), size=100, replace=False)
        pairs = [pairs[i] for i in sampled_indices]

    for i, j in pairs:
        cand_x = _triangulate_indices([i, j])
        if cand_x is None:
            continue
        errs = _compute_reproj_errors(cand_x)
        inliers = [k for k, e in enumerate(errs) if e <= max_reproj_error_px]
        inlier_sum = sum(errs[k] for k in inliers)
        if len(inliers) > len(best_inliers) or (
            len(inliers) == len(best_inliers) and len(inliers) >= 2 and inlier_sum < best_err
        ):
            best_inliers = inliers
            best_x = cand_x
            best_err = inlier_sum

    if len(best_inliers) < 2:
        logger.debug("Triangulation failed: fewer than 2 inliers with reproj error <= %.2f px", max_reproj_error_px)
        return None, float("inf"), []

    final_x = _triangulate_indices(best_inliers)
    if final_x is None:
        final_x = best_x

    final_errs = _compute_reproj_errors(final_x)
    inlier_errs = [final_errs[k] for k in best_inliers]
    mean_err = float(np.mean(inlier_errs)) if inlier_errs else float("inf")

    return final_x, mean_err, best_inliers

ARUCO_DICTIONARY_MAP: dict[str, int] = {
    "DICT_4X4_50": cv2.aruco.DICT_4X4_50,
    "DICT_4X4_100": cv2.aruco.DICT_4X4_100,
    "DICT_4X4_250": cv2.aruco.DICT_4X4_250,
    "DICT_4X4_1000": cv2.aruco.DICT_4X4_1000,
    "DICT_5X5_50": cv2.aruco.DICT_5X5_50,
    "DICT_5X5_100": cv2.aruco.DICT_5X5_100,
    "DICT_5X5_250": cv2.aruco.DICT_5X5_250,
    "DICT_5X5_1000": cv2.aruco.DICT_5X5_1000,
    "DICT_6X6_50": cv2.aruco.DICT_6X6_50,
    "DICT_6X6_100": cv2.aruco.DICT_6X6_100,
    "DICT_6X6_250": cv2.aruco.DICT_6X6_250,
    "DICT_6X6_1000": cv2.aruco.DICT_6X6_1000,
    "DICT_7X7_50": cv2.aruco.DICT_7X7_50,
    "DICT_7X7_100": cv2.aruco.DICT_7X7_100,
    "DICT_7X7_250": cv2.aruco.DICT_7X7_250,
    "DICT_7X7_1000": cv2.aruco.DICT_7X7_1000,
    "DICT_ARUCO_ORIGINAL": cv2.aruco.DICT_ARUCO_ORIGINAL,
}


def resolve_aruco_dictionary(dictionary_name: str) -> int:
    """Resolve dictionary name string to OpenCV constant."""
    name_upper = dictionary_name.strip().upper()
    if name_upper not in ARUCO_DICTIONARY_MAP:
        supported = ", ".join(sorted(ARUCO_DICTIONARY_MAP.keys()))
        raise ScalingConfigError(
            f"Unsupported ArUco dictionary '{dictionary_name}'. Supported options: {supported}"
        )
    return ARUCO_DICTIONARY_MAP[name_upper]


class ArucoDetector:
    """Detects ArUco fiducial markers in captured video keyframes."""

    def __init__(
        self,
        dictionary_name: str = "DICT_4X4_50",
        target_marker_id: Optional[int] = None,
        known_size_mm: float = 50.0,
    ) -> None:
        """Initialize ArUco detector with dictionary and target parameters."""
        self.dictionary_name = dictionary_name
        self.dict_id = resolve_aruco_dictionary(dictionary_name)
        self.target_marker_id = target_marker_id
        if known_size_mm <= 0.0 or not math.isfinite(known_size_mm):
            raise ScalingConfigError(f"Known marker size must be positive and finite, got {known_size_mm}")
        self.known_size_mm = float(known_size_mm)

        self._dictionary = cv2.aruco.getPredefinedDictionary(self.dict_id)
        self._parameters = cv2.aruco.DetectorParameters()
        self._detector = cv2.aruco.ArucoDetector(self._dictionary, self._parameters)

    @property
    def reference_marker(self) -> ReferenceMarker:
        """Construct reference marker specification model."""
        return ReferenceMarker(
            marker_type="aruco",
            marker_id=self.target_marker_id if self.target_marker_id is not None else 0,
            known_size_mm=self.known_size_mm,
            dictionary=self.dictionary_name,
        )

    def detect_in_image(
        self,
        image_path: Path | str,
        target_id: Optional[int] = None,
    ) -> list[MarkerObservation]:
        """Detect markers in a single image file.

        Args:
            image_path: Path to image file on disk.
            target_id: Optional explicit marker ID to filter by. Defaults to self.target_marker_id.

        Returns:
            List of MarkerObservation objects for valid detections matching target_id.

        Raises:
            FileNotFoundError: If image file does not exist.
            ReferenceDetectionError: If image file cannot be decoded.
        """
        path = Path(image_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Image file does not exist: {path}")

        image = cv2.imread(str(path))
        if image is None:
            raise ReferenceDetectionError(f"Failed to read or decode image at: {path}")

        return self.detect_in_array(image, frame_path=str(path), target_id=target_id)

    def detect_in_array(
        self,
        image: np.ndarray,
        frame_path: Optional[str] = None,
        target_id: Optional[int] = None,
    ) -> list[MarkerObservation]:
        """Detect markers in an in-memory numpy BGR or Grayscale image array."""
        if image is None or image.size == 0:
            raise ReferenceDetectionError("Input image array is empty")

        if len(image.shape) == 3 and image.shape[2] == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        elif len(image.shape) == 2:
            gray = image
        else:
            raise ReferenceDetectionError(f"Unsupported image shape for marker detection: {image.shape}")

        corners_list, ids_arr, _ = self._detector.detectMarkers(gray)

        if ids_arr is None or len(corners_list) == 0:
            logger.debug("No ArUco markers detected in frame: %s", frame_path)
            return []

        filter_id = target_id if target_id is not None else self.target_marker_id
        observations: list[MarkerObservation] = []

        for corners_2d, mid in zip(corners_list, ids_arr.flatten()):
            marker_id_val = int(mid)
            if filter_id is not None and marker_id_val != filter_id:
                logger.debug(
                    "Skipping detected marker %d (target is %d) in %s",
                    marker_id_val,
                    filter_id,
                    frame_path,
                )
                continue

            # corners_2d shape is (1, 4, 2)
            pts = corners_2d.reshape((4, 2))
            c0 = (float(pts[0, 0]), float(pts[0, 1]))
            c1 = (float(pts[1, 0]), float(pts[1, 1]))
            c2 = (float(pts[2, 0]), float(pts[2, 1]))
            c3 = (float(pts[3, 0]), float(pts[3, 1]))

            # Calculate 2D edge lengths
            e01 = math.hypot(c1[0] - c0[0], c1[1] - c0[1])
            e12 = math.hypot(c2[0] - c1[0], c2[1] - c1[1])
            e23 = math.hypot(c3[0] - c2[0], c3[1] - c2[1])
            e30 = math.hypot(c0[0] - c3[0], c0[1] - c3[1])

            obs = MarkerObservation(
                marker_id=marker_id_val,
                corners_2d=(c0, c1, c2, c3),
                frame_path=frame_path,
                is_valid=True,
                edge_lengths_2d=[e01, e12, e23, e30],
            )
            observations.append(obs)

        return observations

    def detect_in_frames(
        self,
        frame_paths: Sequence[Path | str],
        target_id: Optional[int] = None,
    ) -> list[MarkerObservation]:
        """Detect markers across multiple keyframe files."""
        all_observations: list[MarkerObservation] = []
        for p in frame_paths:
            obs = self.detect_in_image(p, target_id=target_id)
            all_observations.extend(obs)
        return all_observations

    def triangulate_marker_corners(
        self,
        colmap_dir: Path | str,
        images_dir: Optional[Path | str] = None,
        frame_paths: Optional[Sequence[Path | str]] = None,
        target_id: Optional[int] = None,
        max_reproj_error_px: float = 2.0,
    ) -> tuple[np.ndarray, list[float], list[int]]:
        """Triangulate 4 ArUco marker corners in 3D using registered COLMAP camera poses.

        For all registered keyframes containing detected ArUco markers:
        - Detects 2D corners in each frame.
        - Undistorts corners if camera distortion parameters are present.
        - Constructs 3x4 projection matrix P = K @ [R | t].
        - Triangulates each corner ray across views using DLT and RANSAC outlier rejection.
        - Rejects corner detections with high reprojection error (> max_reproj_error_px).

        Args:
            colmap_dir: Path to COLMAP sparse reconstruction directory (containing cameras and images).
            images_dir: Optional directory containing keyframe image files.
            frame_paths: Optional sequence of explicit frame image paths.
            target_id: Optional marker ID to filter by (defaults to self.target_marker_id).
            max_reproj_error_px: Reprojection error rejection threshold in pixels (default: 2.0).

        Returns:
            Tuple of:
                - corners_3d: (4, 3) float64 numpy array of triangulated 3D corner coordinates.
                - corner_reproj_errors: List of mean reprojection errors for each corner.
                - inlier_view_counts: List of inlier view counts for each corner.

        Raises:
            ReferenceDetectionError: If COLMAP model cannot be loaded, fewer than 2 views observe the marker,
                or triangulation fails / exceeds reprojection error threshold.
        """
        model_path = Path(colmap_dir).resolve()
        try:
            cameras, images = load_colmap_model(model_path)
        except Exception as exc:
            raise ReferenceDetectionError(f"Failed to load COLMAP model from {model_path}: {exc}") from exc

        if not images:
            raise ReferenceDetectionError(f"No registered images found in COLMAP model at {model_path}")

        filter_id = target_id if target_id is not None else self.target_marker_id

        # Build image path lookup table
        frames_lookup: dict[str, Path] = {}
        if frame_paths:
            for fp in frame_paths:
                p = Path(fp).resolve()
                frames_lookup[p.name] = p
                frames_lookup[str(p)] = p

        resolved_images_dir: Optional[Path] = None
        if images_dir:
            resolved_images_dir = Path(images_dir).resolve()

        # Group observations per corner: corner_views[c] = list of (P, (u, v))
        corner_views: list[list[tuple[np.ndarray, tuple[float, float]]]] = [[], [], [], []]
        observed_frame_count = 0

        for img in images.values():
            cam = cameras.get(img.camera_id)
            if cam is None:
                logger.debug("Camera ID %d not found in cameras dictionary for image %s", img.camera_id, img.name)
                continue

            # Resolve image file on disk
            img_file: Optional[Path] = None
            if resolved_images_dir:
                cand1 = resolved_images_dir / img.name
                cand2 = resolved_images_dir / Path(img.name).name
                if cand1.is_file():
                    img_file = cand1
                elif cand2.is_file():
                    img_file = cand2

            if img_file is None and img.name in frames_lookup:
                img_file = frames_lookup[img.name]
            elif img_file is None and Path(img.name).name in frames_lookup:
                img_file = frames_lookup[Path(img.name).name]

            if img_file is None:
                cand_abs = Path(img.name)
                if cand_abs.is_file():
                    img_file = cand_abs

            if img_file is None:
                for cand_parent in [model_path, model_path.parent]:
                    sub = cand_parent / "images" / img.name
                    if sub.is_file():
                        img_file = sub
                        break

            if img_file is None or not img_file.is_file():
                logger.debug("Image file not found for registered image '%s'", img.name)
                continue

            # Detect marker
            try:
                obs_list = self.detect_in_image(img_file, target_id=filter_id)
            except Exception as exc:
                logger.debug("Marker detection skipped on %s: %s", img_file, exc)
                continue

            if not obs_list:
                continue

            # If multiple markers, pick the one with the largest perimeter
            best_obs = max(obs_list, key=lambda o: sum(o.edge_lengths_2d) if o.edge_lengths_2d else 0.0)
            corners_2d = best_obs.corners_2d

            # Undistort 2D corners if camera distortion is defined
            if cam.dist_coeffs is not None and len(cam.dist_coeffs) > 0 and not np.all(cam.dist_coeffs == 0):
                pts_arr = np.array(corners_2d, dtype=np.float32).reshape(-1, 1, 2)
                pts_undist = cv2.undistortPoints(
                    pts_arr,
                    np.asarray(cam.K, dtype=np.float64),
                    np.asarray(cam.dist_coeffs, dtype=np.float64),
                    P=np.asarray(cam.K, dtype=np.float64),
                ).reshape(-1, 2)
                undist_corners = [(float(p[0]), float(p[1])) for p in pts_undist]
            else:
                undist_corners = corners_2d

            # Construct 3x4 projection matrix P = K @ [R | t]
            tvec_col = img.tvec.reshape((3, 1))
            Rt = np.hstack([img.R, tvec_col])
            P = cam.K @ Rt

            for c in range(4):
                corner_views[c].append((P, undist_corners[c]))

            observed_frame_count += 1

        if observed_frame_count < 2:
            raise ReferenceDetectionError(
                f"ArUco marker (ID {filter_id}) observed in only {observed_frame_count} registered COLMAP image(s). "
                f"At least 2 registered views are required for 3D triangulation."
            )

        corners_3d: list[np.ndarray] = []
        reproj_errors: list[float] = []
        inlier_counts: list[int] = []

        for c in range(4):
            projs = [item[0] for item in corner_views[c]]
            pts_2d = [item[1] for item in corner_views[c]]
            pt_3d, err, inliers = triangulate_multiview_point(
                proj_matrices=projs,
                points_2d=pts_2d,
                max_reproj_error_px=max_reproj_error_px,
            )
            if pt_3d is None:
                raise ReferenceDetectionError(
                    f"Failed to triangulate 3D coordinates for marker corner {c}: "
                    f"reprojection error exceeded {max_reproj_error_px:.1f} px or fewer than 2 inlier views."
                )
            corners_3d.append(pt_3d)
            reproj_errors.append(err)
            inlier_counts.append(len(inliers))

        corners_arr = np.array(corners_3d, dtype=np.float64)
        return corners_arr, reproj_errors, inlier_counts

    def compute_reconstructed_marker_size(
        self,
        colmap_dir: Path | str,
        images_dir: Optional[Path | str] = None,
        frame_paths: Optional[Sequence[Path | str]] = None,
        target_id: Optional[int] = None,
        max_reproj_error_px: float = 2.0,
    ) -> tuple[float, np.ndarray, list[float], list[float]]:
        """Compute reconstructed 3D marker size (L_sfm) from COLMAP reconstruction.

        Triangulates marker corners into 3D world coordinates, computes Euclidean distances
        between perimeter corners, and determines L_sfm = median([L01, L12, L23, L30]).

        Args:
            colmap_dir: Path to COLMAP sparse directory.
            images_dir: Optional directory containing keyframe images.
            frame_paths: Optional sequence of frame paths.
            target_id: Optional marker ID to filter by.
            max_reproj_error_px: Reprojection error rejection threshold (default: 2.0 px).

        Returns:
            Tuple of:
                - l_sfm: Reconstructed marker size in SfM coordinate units.
                - corners_3d: (4, 3) float64 array of triangulated 3D corners.
                - edge_lengths: 4 perimeter Euclidean lengths [L01, L12, L23, L30].
                - reproj_errors: 4 corner mean reprojection errors.
        """
        corners_3d, reproj_errors, _ = self.triangulate_marker_corners(
            colmap_dir=colmap_dir,
            images_dir=images_dir,
            frame_paths=frame_paths,
            target_id=target_id,
            max_reproj_error_px=max_reproj_error_px,
        )

        pts = corners_3d
        e01 = float(np.linalg.norm(pts[1] - pts[0]))
        e12 = float(np.linalg.norm(pts[2] - pts[1]))
        e23 = float(np.linalg.norm(pts[3] - pts[2]))
        e30 = float(np.linalg.norm(pts[0] - pts[3]))
        edge_lengths = [e01, e12, e23, e30]
        l_sfm = float(np.median(edge_lengths))

        mid = target_id if target_id is not None else (self.target_marker_id or 0)
        logger.info(
            "Triangulated 3D ArUco marker (ID %d): L_sfm=%.6f (edges: [%.6f, %.6f, %.6f, %.6f], mean reproj error=%.2f px)",
            mid,
            l_sfm,
            e01, e12, e23, e30,
            float(np.mean(reproj_errors)),
        )

        return l_sfm, corners_3d, edge_lengths, reproj_errors

    @staticmethod
    def generate_marker_image(
        dictionary_name: str = "DICT_4X4_50",
        marker_id: int = 0,
        size_px: int = 200,
        margin_px: int = 50,
    ) -> np.ndarray:
        """Utility to generate a clean synthetic ArUco marker image with quiet margin."""
        dict_id = resolve_aruco_dictionary(dictionary_name)
        dictionary = cv2.aruco.getPredefinedDictionary(dict_id)
        marker_img = cv2.aruco.generateImageMarker(dictionary, marker_id, size_px)
        if margin_px > 0:
            bordered = cv2.copyMakeBorder(
                marker_img,
                margin_px,
                margin_px,
                margin_px,
                margin_px,
                cv2.BORDER_CONSTANT,
                value=255,
            )
            return bordered
        return marker_img
