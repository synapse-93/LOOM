"""Unit tests for ArUco detector and dictionary resolution."""

from __future__ import annotations

from pathlib import Path
import cv2
import numpy as np
import pytest

from loom.scaling.aruco import (
    ARUCO_DICTIONARY_MAP,
    ArucoDetector,
    load_colmap_model,
    read_colmap_cameras_text,
    read_colmap_images_text,
    resolve_aruco_dictionary,
    triangulate_multiview_point,
)
from loom.scaling.exceptions import ReferenceDetectionError, ScalingConfigError


def test_dictionary_resolution() -> None:
    """Verify dictionary resolution resolves standard names and rejects invalid names."""
    dict_id = resolve_aruco_dictionary("DICT_4X4_50")
    assert dict_id == cv2.aruco.DICT_4X4_50

    dict_id_case = resolve_aruco_dictionary("dict_6x6_250")
    assert dict_id_case == cv2.aruco.DICT_6X6_250

    with pytest.raises(ScalingConfigError):
        resolve_aruco_dictionary("NON_EXISTENT_DICT")


def test_detector_configuration_validation() -> None:
    """Verify ArucoDetector rejects non-positive known sizes."""
    with pytest.raises(ScalingConfigError):
        ArucoDetector(known_size_mm=-5.0)

    with pytest.raises(ScalingConfigError):
        ArucoDetector(known_size_mm=0.0)

    with pytest.raises(ScalingConfigError):
        ArucoDetector(dictionary_name="INVALID_DICT")


def test_synthetic_marker_generation_and_detection(tmp_path: Path) -> None:
    """Verify generating a synthetic marker image and detecting it returns 4 corners and ID."""
    detector = ArucoDetector(dictionary_name="DICT_4X4_50", target_marker_id=0, known_size_mm=50.0)
    marker_img = ArucoDetector.generate_marker_image("DICT_4X4_50", marker_id=0, size_px=200, margin_px=40)

    img_path = tmp_path / "test_marker_0.png"
    cv2.imwrite(str(img_path), marker_img)

    observations = detector.detect_in_image(img_path)
    assert len(observations) == 1

    obs = observations[0]
    assert obs.marker_id == 0
    assert obs.is_valid is True
    assert len(obs.corners_2d) == 4
    assert obs.edge_lengths_2d is not None
    assert len(obs.edge_lengths_2d) == 4
    # With size 200px and 40px border, corners should be around ~199px apart
    for edge in obs.edge_lengths_2d:
        assert edge == pytest.approx(199.0, abs=3.0)


def test_target_marker_id_filtering(tmp_path: Path) -> None:
    """Verify that detector filters for target_id and ignores other IDs."""
    detector = ArucoDetector(dictionary_name="DICT_4X4_50", target_marker_id=4, known_size_mm=50.0)
    # Generate marker 0
    marker_img = ArucoDetector.generate_marker_image("DICT_4X4_50", marker_id=0, size_px=200, margin_px=40)
    img_path = tmp_path / "marker_0.png"
    cv2.imwrite(str(img_path), marker_img)

    # Should find 0 observations matching target_id=4
    obs = detector.detect_in_image(img_path)
    assert len(obs) == 0

    # Overriding target_id to 0 should find it
    obs_override = detector.detect_in_image(img_path, target_id=0)
    assert len(obs_override) == 1
    assert obs_override[0].marker_id == 0


def test_empty_or_corrupt_image(tmp_path: Path) -> None:
    """Verify handling of invalid or unreadable image files."""
    detector = ArucoDetector()
    corrupt_file = tmp_path / "corrupt.png"
    corrupt_file.write_bytes(b"not an image file")

    with pytest.raises(ReferenceDetectionError):
        detector.detect_in_image(corrupt_file)

    blank_img = np.ones((100, 100, 3), dtype=np.uint8) * 255
    obs_blank = detector.detect_in_array(blank_img)
    assert len(obs_blank) == 0


def test_read_colmap_cameras_and_images_text(tmp_path: Path) -> None:
    """Verify parsing COLMAP cameras.txt and images.txt files."""
    cameras_txt = tmp_path / "cameras.txt"
    cameras_txt.write_text(
        "# Camera list:\n"
        "1 PINHOLE 800 600 1000.0 1000.0 400.0 300.0\n"
        "2 RADIAL 1920 1080 1500.0 960.0 540.0 0.05 -0.01\n",
        encoding="utf-8",
    )
    cams = read_colmap_cameras_text(cameras_txt)
    assert len(cams) == 2
    assert cams[1].model == "PINHOLE"
    assert cams[1].width == 800
    assert cams[1].height == 600
    assert cams[1].K.shape == (3, 3)
    assert cams[1].K[0, 0] == 1000.0
    assert cams[2].dist_coeffs is not None
    assert len(cams[2].dist_coeffs) >= 2

    images_txt = tmp_path / "images.txt"
    images_txt.write_text(
        "# Image list:\n"
        "1 1.0 0.0 0.0 0.0 0.0 0.0 -2.0 1 frame_01.png\n"
        "0.0 0.0 -1\n"
        "2 0.7071068 0.0 0.7071068 0.0 0.5 0.0 -2.0 1 frame_02.png\n"
        "0.0 0.0 -1\n",
        encoding="utf-8",
    )
    imgs = read_colmap_images_text(images_txt)
    assert len(imgs) == 2
    assert imgs[1].name == "frame_01.png"
    assert imgs[1].R.shape == (3, 3)
    np.testing.assert_allclose(imgs[1].R, np.eye(3), atol=1e-5)
    assert imgs[2].camera_id == 1

    loaded_cams, loaded_imgs = load_colmap_model(tmp_path)
    assert len(loaded_cams) == 2
    assert len(loaded_imgs) == 2


def test_triangulate_multiview_point_precision() -> None:
    """Verify triangulate_multiview_point recovers exact 3D point from multiple views."""
    K = np.array([[1000.0, 0.0, 400.0], [0.0, 1000.0, 300.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    pt_world = np.array([0.15, -0.25, 2.5], dtype=np.float64)

    cam_centers = [[-0.3, 0.0, 0.0], [0.0, 0.0, 0.0], [0.3, 0.0, 0.0]]
    R = np.eye(3)
    projs = []
    pts_2d = []

    for c in cam_centers:
        t = -R @ np.array(c)
        Rt = np.hstack([R, t.reshape(3, 1)])
        P = K @ Rt
        projs.append(P)

        cam_coord = R @ pt_world + t
        u = K[0, 0] * cam_coord[0] / cam_coord[2] + K[0, 2]
        v = K[1, 1] * cam_coord[1] / cam_coord[2] + K[1, 2]
        pts_2d.append((u, v))

    tri_pt, err, inliers = triangulate_multiview_point(projs, pts_2d, max_reproj_error_px=2.0)
    assert tri_pt is not None
    assert len(inliers) == 3
    assert err < 1e-6
    np.testing.assert_allclose(tri_pt, pt_world, atol=1e-5)


def test_triangulate_multiview_point_outlier_rejection() -> None:
    """Verify triangulate_multiview_point rejects rays exceeding max_reproj_error_px threshold."""
    K = np.array([[1000.0, 0.0, 400.0], [0.0, 1000.0, 300.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    pt_world = np.array([0.05, -0.05, 2.0], dtype=np.float64)

    cam_centers = [[-0.3, 0.0, 0.0], [-0.1, 0.0, 0.0], [0.1, 0.0, 0.0], [0.3, 0.0, 0.0]]
    R = np.eye(3)
    projs = []
    pts_2d = []

    for c in cam_centers:
        t = -R @ np.array(c)
        Rt = np.hstack([R, t.reshape(3, 1)])
        P = K @ Rt
        projs.append(P)

        cam_coord = R @ pt_world + t
        u = K[0, 0] * cam_coord[0] / cam_coord[2] + K[0, 2]
        v = K[1, 1] * cam_coord[1] / cam_coord[2] + K[1, 2]
        pts_2d.append((u, v))

    # Corrupt view index 3 with 15px error (> 2.0px)
    pts_2d[3] = (pts_2d[3][0] + 15.0, pts_2d[3][1] + 15.0)

    tri_pt, err, inliers = triangulate_multiview_point(projs, pts_2d, max_reproj_error_px=2.0)
    assert tri_pt is not None
    assert 3 not in inliers
    assert set(inliers) == {0, 1, 2}
    assert err < 1e-4
    np.testing.assert_allclose(tri_pt, pt_world, atol=1e-4)


def test_triangulate_multiview_point_insufficient_views() -> None:
    """Verify triangulation fails when fewer than 2 views or inliers are provided."""
    P = np.eye(3, 4)
    pt, err, inliers = triangulate_multiview_point([P], [(10.0, 10.0)], max_reproj_error_px=2.0)
    assert pt is None
    assert inliers == []


def _setup_synthetic_colmap_scene(tmp_path: Path) -> tuple[Path, Path, float]:
    """Create a synthetic COLMAP sparse reconstruction directory and rendered marker images."""
    colmap_dir = tmp_path / "sparse"
    colmap_dir.mkdir(parents=True, exist_ok=True)
    images_dir = tmp_path / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    cameras_txt = colmap_dir / "cameras.txt"
    cameras_txt.write_text(
        "# Camera list:\n"
        "1 PINHOLE 800 600 1000.0 1000.0 400.0 300.0\n",
        encoding="utf-8",
    )

    c_world = np.array([
        [-0.05, -0.05, 2.0],
        [ 0.05, -0.05, 2.0],
        [ 0.05,  0.05, 2.0],
        [-0.05,  0.05, 2.0],
    ], dtype=np.float64)

    cam_centers = [[-0.2, 0.0, 0.0], [0.0, 0.0, 0.0], [0.2, 0.0, 0.0]]
    R = np.eye(3, dtype=np.float64)
    K = np.array([[1000.0, 0.0, 400.0], [0.0, 1000.0, 300.0], [0.0, 0.0, 1.0]], dtype=np.float64)

    images_lines = [
        "# Image list:\n",
    ]

    marker_raw = ArucoDetector.generate_marker_image("DICT_4X4_50", marker_id=0, size_px=200, margin_px=0)
    pts_src = np.array([[0, 0], [200, 0], [200, 200], [0, 200]], dtype=np.float32)

    for i, center in enumerate(cam_centers, start=1):
        t = -R @ np.array(center, dtype=np.float64)
        name = f"frame_{i:02d}.png"
        images_lines.append(f"{i} 1.0 0.0 0.0 0.0 {t[0]:.6f} {t[1]:.6f} {t[2]:.6f} 1 {name}\n")
        images_lines.append("0.0 0.0 -1\n")

        cam_coords = (R @ c_world.T + t.reshape(3, 1)).T
        u = K[0, 0] * cam_coords[:, 0] / cam_coords[:, 2] + K[0, 2]
        v = K[1, 1] * cam_coords[:, 1] / cam_coords[:, 2] + K[1, 2]
        pts_dst = np.column_stack([u, v]).astype(np.float32)

        H = cv2.getPerspectiveTransform(pts_src, pts_dst)
        frame = np.ones((600, 800, 3), dtype=np.uint8) * 255
        cv2.warpPerspective(
            cv2.cvtColor(marker_raw, cv2.COLOR_GRAY2BGR),
            H,
            (800, 600),
            dst=frame,
            borderMode=cv2.BORDER_TRANSPARENT,
        )
        cv2.imwrite(str(images_dir / name), frame)

    images_txt = colmap_dir / "images.txt"
    images_txt.write_text("".join(images_lines), encoding="utf-8")

    return colmap_dir, images_dir, 0.1


def test_triangulate_marker_corners_and_compute_size(tmp_path: Path) -> None:
    """Verify triangulate_marker_corners and compute_reconstructed_marker_size on synthetic COLMAP scene."""
    colmap_dir, images_dir, expected_size = _setup_synthetic_colmap_scene(tmp_path)

    detector = ArucoDetector(dictionary_name="DICT_4X4_50", target_marker_id=0, known_size_mm=50.0)

    corners_3d, reproj_errs, inliers = detector.triangulate_marker_corners(
        colmap_dir=colmap_dir,
        images_dir=images_dir,
        max_reproj_error_px=2.0,
    )
    assert corners_3d.shape == (4, 3)
    assert len(reproj_errs) == 4
    for err in reproj_errs:
        assert err <= 2.0
    for count in inliers:
        assert count == 3

    l_sfm, corners, edges, errs = detector.compute_reconstructed_marker_size(
        colmap_dir=colmap_dir,
        images_dir=images_dir,
        max_reproj_error_px=2.0,
    )
    assert len(edges) == 4
    assert l_sfm == pytest.approx(expected_size, rel=0.03)


def test_triangulate_marker_corners_insufficient_views(tmp_path: Path) -> None:
    """Verify triangulate_marker_corners raises ReferenceDetectionError when fewer than 2 views observe marker."""
    colmap_dir, images_dir, _ = _setup_synthetic_colmap_scene(tmp_path)
    # Target marker ID 99 does not exist in the images
    detector = ArucoDetector(dictionary_name="DICT_4X4_50", target_marker_id=99)

    with pytest.raises(ReferenceDetectionError, match="observed in only 0 registered"):
        detector.triangulate_marker_corners(colmap_dir=colmap_dir, images_dir=images_dir)

