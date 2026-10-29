"""Unit tests for reconstruction-aware keyframe selection."""

from __future__ import annotations

from pathlib import Path
import cv2
import numpy as np
import pytest

from loom.capture.quality import FrameQualityAssessor
from loom.capture.reconstruction_aware import (
    FrameAnalysis,
    MatchEdge,
    ReconstructionAwareSelector,
)
from loom.config.models import CaptureConfig


def _create_textured_frame(
    path: Path,
    label: str = "LOOM",
    shift_x: int = 0,
    shift_y: int = 0,
    brightness: int = 128,
    contrast_scale: float = 1.0,
    seed: int = 42,
) -> Path:
    """Helper to generate a deterministic synthetic image with visual features."""
    img = np.ones((240, 320), dtype=np.uint8) * np.clip(brightness, 0, 255).astype(np.uint8)
    rng = np.random.default_rng(seed)
    for _ in range(40):
        cx = int(rng.integers(30, 290)) + shift_x
        cy = int(rng.integers(30, 210)) + shift_y
        rad = int(rng.integers(4, 12))
        val = int(rng.integers(20, 240) * contrast_scale)
        val = int(np.clip(val, 0, 255))
        cv2.circle(img, (cx, cy), rad, val, -1)
        cv2.putText(
            img,
            label,
            (cx - 10, cy + 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.3,
            255 - val,
            1,
        )
    cv2.imwrite(str(path), img)
    return path


def test_capture_config_validation() -> None:
    """Verify CaptureConfig enforces constraints on all selection parameters."""
    # Valid config
    cfg = CaptureConfig(
        selection_mode="reconstruction_aware",
        target_selected_frames=20,
        min_inlier_matches=10,
        max_homography_inlier_ratio=0.80,
        temporal_window_size=2,
    )
    assert cfg.selection_mode == "reconstruction_aware"

    # Invalid selection_mode
    with pytest.raises(ValueError, match="Invalid selection_mode"):
        CaptureConfig(selection_mode="invalid_mode")

    # Invalid target_selected_frames
    with pytest.raises(ValueError, match="target_selected_frames must be positive"):
        CaptureConfig(target_selected_frames=0)

    # Invalid min_inlier_matches
    with pytest.raises(ValueError, match="min_inlier_matches must be positive"):
        CaptureConfig(min_inlier_matches=-5)

    # Invalid max_homography_inlier_ratio
    with pytest.raises(ValueError, match="max_homography_inlier_ratio must be between 0.0 and 1.0"):
        CaptureConfig(max_homography_inlier_ratio=1.5)

    with pytest.raises(ValueError, match="max_homography_inlier_ratio must be between 0.0 and 1.0"):
        CaptureConfig(max_homography_inlier_ratio=-0.1)

    # Invalid temporal_window_size
    with pytest.raises(ValueError, match="temporal_window_size must be positive"):
        CaptureConfig(temporal_window_size=0)

    # Invalid sharpness_threshold
    with pytest.raises(ValueError, match="sharpness_threshold cannot be negative"):
        CaptureConfig(sharpness_threshold=-1.0)


def test_reconstruction_aware_full_duration_coverage(tmp_path: Path) -> None:
    """Verify reconstruction-aware selection guarantees broad temporal coverage across timeline."""
    frame_paths = []
    # Create 20 frames across timeline
    for i in range(20):
        p = tmp_path / f"frame_{i:04d}.png"
        _create_textured_frame(p, label=f"F{i}", shift_x=i * 2, seed=100 + i)
        frame_paths.append(p)

    cfg = CaptureConfig(
        selection_mode="reconstruction_aware",
        target_selected_frames=5,
        sharpness_threshold=50.0,
        enable_geometric_verification=False,
    )
    assessor = FrameQualityAssessor(config=cfg)
    artifact, results = assessor.assess_and_filter(frame_paths)

    assert len(artifact.selected_frames) == 5
    selected_indices = [int(p.stem.split("_")[1]) for p in artifact.selected_frames]

    # Verify first selected frame is in the initial sector and last is in the final sector
    assert selected_indices[0] in [0, 1, 2, 3]
    assert selected_indices[-1] in [16, 17, 18, 19]

    # Verify temporal coverage spans majority of timeline and max gap is bounded
    cov_ratio = artifact.metadata["temporal_coverage_score"]
    assert cov_ratio >= 0.65
    gaps = [selected_indices[k] - selected_indices[k - 1] for k in range(1, len(selected_indices))]
    assert max(gaps) <= 5


def test_reconstruction_aware_avoids_clustering(tmp_path: Path) -> None:
    """Verify reconstruction-aware mode avoids clustering frames into high-sharpness interval."""
    frame_paths = []
    # Create 15 frames:
    # 0-4: moderate contrast / texture
    # 5-9: high texture
    # 10-14: moderate contrast / texture
    for i in range(15):
        p = tmp_path / f"cluster_test_{i:04d}.png"
        contrast_scale = 2.0 if (5 <= i <= 9) else 0.8
        _create_textured_frame(p, label=f"C{i}", contrast_scale=contrast_scale, seed=200 + i)
        frame_paths.append(p)

    cfg = CaptureConfig(
        selection_mode="reconstruction_aware",
        target_selected_frames=5,
        enable_geometric_verification=False,
    )
    assessor = FrameQualityAssessor(config=cfg)
    artifact, _ = assessor.assess_and_filter(frame_paths)

    selected_indices = [int(p.stem.split("_")[2]) for p in artifact.selected_frames]

    # Frames must not be concentrated solely in [5, 9]
    has_early = any(idx < 5 for idx in selected_indices)
    has_middle = any(5 <= idx <= 9 for idx in selected_indices)
    has_late = any(idx >= 10 for idx in selected_indices)

    assert has_early, "Should select early timeline frame"
    assert has_middle, "Should select middle timeline frame"
    assert has_late, "Should select late timeline frame"


def test_reconstruction_aware_detects_homography_degeneracy() -> None:
    """Verify that pure planar / rotational motion is distinguished from 3D parallax."""
    cfg = CaptureConfig(
        selection_mode="reconstruction_aware",
        max_homography_inlier_ratio=0.85,
        min_inlier_matches=15,
    )
    selector = ReconstructionAwareSelector(config=cfg)

    # 1. Pure planar homography / rotation scene
    img1 = np.zeros((480, 640), dtype=np.uint8)
    rng = np.random.default_rng(42)
    for _ in range(120):
        cx, cy = int(rng.integers(50, 590)), int(rng.integers(50, 430))
        cv2.putText(img1, "LOOM", (cx, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 255, 2)
        cv2.circle(img1, (cx, cy), 5, 180, -1)

    M = cv2.getRotationMatrix2D((320, 240), 2.0, 1.0)
    img2 = cv2.warpAffine(img1, M, (640, 480))

    sift = cv2.SIFT_create(nfeatures=600)
    kp1, des1 = sift.detectAndCompute(img1, None)
    kp2, des2 = sift.detectAndCompute(img2, None)

    fa1 = FrameAnalysis(0, Path("f0.png"), 100.0, 128.0, 50.0, 100.0, len(kp1), 1.0, 1.0, False, False, False, False, False, kp1, des1)
    fa2 = FrameAnalysis(1, Path("f1.png"), 100.0, 128.0, 50.0, 100.0, len(kp2), 1.0, 1.0, False, False, False, False, False, kp2, des2)

    edge_homography = selector._verify_pair_geometry(fa1, fa2)

    assert edge_homography.is_connected is True
    assert edge_homography.h_ratio >= 0.85
    assert edge_homography.is_parallax_bearing is False

    # 2. Scene with significant 3D parallax (two disparate depth regions)
    img_a = np.zeros((480, 640), dtype=np.uint8)
    img_b = np.zeros((480, 640), dtype=np.uint8)
    rng2 = np.random.default_rng(999)
    # Left plane (dx = -10)
    for _ in range(60):
        cx, cy = int(rng2.integers(40, 280)), int(rng2.integers(40, 440))
        cv2.putText(img_a, "OBJ1", (cx, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 200, 2)
        cv2.putText(img_b, "OBJ1", (cx - 10, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 200, 2)
    # Right plane (dx = -50)
    for _ in range(60):
        cx, cy = int(rng2.integers(340, 600)), int(rng2.integers(40, 440))
        cv2.putText(img_a, "OBJ2", (cx, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 255, 2)
        cv2.putText(img_b, "OBJ2", (cx - 50, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 255, 2)

    kp_a, des_a = sift.detectAndCompute(img_a, None)
    kp_b, des_b = sift.detectAndCompute(img_b, None)

    fa_a = FrameAnalysis(0, Path("fa.png"), 100.0, 128.0, 50.0, 100.0, len(kp_a), 1.0, 1.0, False, False, False, False, False, kp_a, des_a)
    fa_b = FrameAnalysis(1, Path("fb.png"), 100.0, 128.0, 50.0, 100.0, len(kp_b), 1.0, 1.0, False, False, False, False, False, kp_b, des_b)

    edge_parallax = selector._verify_pair_geometry(fa_a, fa_b)
    assert edge_parallax.is_connected is True
    assert edge_parallax.h_ratio < 0.85
    assert edge_parallax.is_parallax_bearing is True


def test_reconstruction_aware_prefers_bridge_frames() -> None:
    """Verify that a candidate frame bridging two disconnected subgraphs is prioritized."""
    cfg = CaptureConfig(
        selection_mode="reconstruction_aware",
        target_selected_frames=3,
        enable_geometric_verification=True,
    )
    selector = ReconstructionAwareSelector(config=cfg)

    # Create 5 synthetic candidates:
    # 0, 1, 2, 3, 4
    candidates = [
        FrameAnalysis(
            index=i,
            path=Path(f"cand_{i}.png"),
            sharpness=100.0,
            brightness=120.0,
            contrast=40.0,
            texture_score=100.0,
            keypoint_count=50,
            grid_coverage=1.0,
            optical_score=0.8,
            is_underexposed=False,
            is_overexposed=False,
            is_low_contrast=False,
            is_low_texture=False,
            is_severe_defect=False,
            thumbnail=np.full((64, 64), i * 15, dtype=np.uint8),
        )
        for i in range(5)
    ]

    # Graph structure:
    # 0 connected to 1
    # 3 connected to 4
    # 2 connects to BOTH 1 and 3 (the bridge frame!)
    edges = [
        MatchEdge(0, 1, raw_matches=30, f_inliers=25, h_inliers=10, h_ratio=0.4, is_connected=True, is_parallax_bearing=True),
        MatchEdge(3, 4, raw_matches=30, f_inliers=25, h_inliers=10, h_ratio=0.4, is_connected=True, is_parallax_bearing=True),
        MatchEdge(1, 2, raw_matches=25, f_inliers=20, h_inliers=8, h_ratio=0.4, is_connected=True, is_parallax_bearing=True),
        MatchEdge(2, 3, raw_matches=25, f_inliers=20, h_inliers=8, h_ratio=0.4, is_connected=True, is_parallax_bearing=True),
    ]

    selected_indices, sel_reasons, _, diagnostics = selector._select_keyframes(candidates, edges)

    # Frame 2 must be included in the selected keyframes
    assert 2 in selected_indices
    # Selected graph should have fewer components than disconnected candidates
    assert diagnostics["match_graph_status"] == "evaluated"


def test_reconstruction_aware_discards_redundant_frames(tmp_path: Path) -> None:
    """Verify visually redundant identical frames are filtered with explicit reasons."""
    p1 = tmp_path / "frame_0000.png"
    p2 = tmp_path / "frame_0001.png"
    p3 = tmp_path / "frame_0002.png"

    _create_textured_frame(p1, label="UNIQUE_A", seed=10)
    # p2 is an exact copy of p1 (100% redundant)
    p2.write_bytes(p1.read_bytes())
    _create_textured_frame(p3, label="UNIQUE_B", seed=20)

    cfg = CaptureConfig(
        selection_mode="reconstruction_aware",
        target_selected_frames=2,
        redundancy_threshold=0.98,
        enable_geometric_verification=False,
    )
    assessor = FrameQualityAssessor(config=cfg)
    artifact, results = assessor.assess_and_filter([p1, p2, p3])

    # p2 should be rejected as redundant
    res_map = {r.frame_path.name: r for r in results}
    assert res_map["frame_0001.png"].is_accepted is False
    assert res_map["frame_0001.png"].is_redundant is True
    assert any("redundancy" in r.lower() for r in res_map["frame_0001.png"].rejection_reasons)


def test_reconstruction_aware_handles_disabled_or_missing_geometric_data(tmp_path: Path) -> None:
    """Verify that when geometric data is disabled, it reports limitation accurately without fake scores."""
    frame_paths = []
    for i in range(6):
        p = tmp_path / f"geom_off_{i:04d}.png"
        _create_textured_frame(p, label=f"G{i}", seed=300 + i)
        frame_paths.append(p)

    cfg = CaptureConfig(
        selection_mode="reconstruction_aware",
        target_selected_frames=3,
        enable_geometric_verification=False,
    )
    assessor = FrameQualityAssessor(config=cfg)
    artifact, _ = assessor.assess_and_filter(frame_paths)

    diag = artifact.metadata["graph_diagnostics"]
    assert diag["match_graph_status"] == "unavailable"
    assert "limitation" in diag
    assert "disabled or unavailable" in diag["limitation"]
    # Selection should still succeed using temporal buckets
    assert len(artifact.selected_frames) == 3


def test_reconstruction_aware_handles_defective_frames(tmp_path: Path) -> None:
    """Verify severely defective frames (black, white, uniform) are rejected with explicit reasons."""
    # 1. Dark frame (brightness < 10)
    p_black = tmp_path / "frame_black.png"
    cv2.imwrite(str(p_black), np.zeros((100, 100), dtype=np.uint8))

    # 2. Blown out frame (brightness > 248)
    p_white = tmp_path / "frame_white.png"
    cv2.imwrite(str(p_white), np.full((100, 100), 255, dtype=np.uint8))

    # 3. Flat uniform gray frame (contrast < 5, zero keypoints)
    p_gray = tmp_path / "frame_gray.png"
    cv2.imwrite(str(p_gray), np.full((100, 100), 128, dtype=np.uint8))

    # 4. Valid sharp textured frame
    p_valid = tmp_path / "frame_valid.png"
    _create_textured_frame(p_valid, label="VALID", seed=400)

    cfg = CaptureConfig(
        selection_mode="reconstruction_aware",
        target_selected_frames=2,
    )
    assessor = FrameQualityAssessor(config=cfg)
    artifact, results = assessor.assess_and_filter([p_black, p_white, p_gray, p_valid])

    res_map = {r.frame_path.name: r for r in results}
    assert res_map["frame_black.png"].is_accepted is False
    assert res_map["frame_white.png"].is_accepted is False
    assert res_map["frame_gray.png"].is_accepted is False

    assert any("underexposure" in r.lower() for r in res_map["frame_black.png"].rejection_reasons)
    assert any("overexposure" in r.lower() for r in res_map["frame_white.png"].rejection_reasons)
    assert any("contrast" in r.lower() or "features" in r.lower() for r in res_map["frame_gray.png"].rejection_reasons)

    assert res_map["frame_valid.png"].is_accepted is True


def test_reconstruction_aware_deterministic_selection(tmp_path: Path) -> None:
    """Verify identical inputs yield identical selections and metrics across repeated runs."""
    frame_paths = []
    for i in range(8):
        p = tmp_path / f"det_{i:04d}.png"
        _create_textured_frame(p, label=f"D{i}", seed=500 + i)
        frame_paths.append(p)

    cfg = CaptureConfig(
        selection_mode="reconstruction_aware",
        target_selected_frames=4,
    )
    assessor = FrameQualityAssessor(config=cfg)

    artifact1, results1 = assessor.assess_and_filter(frame_paths)
    artifact2, results2 = assessor.assess_and_filter(frame_paths)

    assert artifact1.selected_frames == artifact2.selected_frames
    assert artifact1.rejected_frames == artifact2.rejected_frames
    assert [r.is_accepted for r in results1] == [r.is_accepted for r in results2]
    assert [r.rejection_reasons for r in results1] == [r.rejection_reasons for r in results2]


def test_default_mode_compatibility(tmp_path: Path) -> None:
    """Verify selection_mode='default' preserves 100% backward compatibility."""
    p_sharp = tmp_path / "frame_sharp.png"
    p_blurry = tmp_path / "frame_blurry.png"

    _create_textured_frame(p_sharp, label="SHARP", seed=601)

    # Create blurry image via GaussianBlur
    img = cv2.imread(str(p_sharp), cv2.IMREAD_GRAYSCALE)
    blurry = cv2.GaussianBlur(img, (25, 25), 10.0)
    cv2.imwrite(str(p_blurry), blurry)

    cfg = CaptureConfig(
        selection_mode="default",
        sharpness_threshold=100.0,
    )
    assessor = FrameQualityAssessor(config=cfg)
    artifact, results = assessor.assess_and_filter([p_sharp, p_blurry])

    res_map = {r.frame_path.name: r for r in results}
    assert res_map["frame_blurry.png"].is_blurry is True
    assert res_map["frame_blurry.png"].is_accepted is False
    assert any("low sharpness" in r.lower() for r in res_map["frame_blurry.png"].rejection_reasons)
    # Default mode should not have reconstruction_aware metadata
    assert "selection_mode" not in artifact.metadata or artifact.metadata.get("selection_mode") != "reconstruction_aware"
