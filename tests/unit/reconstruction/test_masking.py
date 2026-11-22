"""CPU unit tests for memory-safe semantic foreground masking and visual audit (masking.py)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from loom.reconstruction.masking import ForegroundMasker, postprocess_alpha_mask


def test_postprocess_alpha_mask_threshold_speckles_and_central_component() -> None:
    """Verify thresholding >=128, speckle removal, and retention of central primary component."""
    h, w = 200, 200
    alpha = np.zeros((h, w), dtype=np.uint8)

    # 1. Sub-threshold gray haze (<128) -> must be discarded
    alpha[10:40, 10:40] = 100

    # 2. Central object (~12% area) -> must be retained
    cv2.circle(alpha, center=(100, 100), radius=35, color=240, thickness=-1)

    # 3. Secondary off-center background clutter (~6% area, near corner) -> must be dropped
    cv2.rectangle(alpha, (150, 150), (198, 198), color=255, thickness=-1)

    # 4. Tiny disconnected speckles (<1% area) -> must be removed
    alpha[5:8, 180:183] = 255
    alpha[185:187, 10:12] = 255

    cleaned = postprocess_alpha_mask(alpha, alpha_threshold=128, morph_kernel_size=3, min_area_ratio=0.01)

    assert cleaned.dtype == np.uint8
    assert set(np.unique(cleaned)).issubset({0, 255})
    assert cleaned[100, 100] == 255
    assert cleaned[20, 20] == 0
    assert cleaned[175, 175] == 0
    assert cleaned[6, 181] == 0
    assert cleaned[185, 10] == 0


def test_postprocess_alpha_mask_discards_only_tiny_islands() -> None:
    """Verify tiny islands (<1% of image area) with no real subject yield an empty mask."""
    alpha = np.zeros((200, 200), dtype=np.uint8)
    alpha[95:105, 95:105] = 255  # 0.25% < 1%
    cleaned = postprocess_alpha_mask(alpha, min_area_ratio=0.01)
    assert np.count_nonzero(cleaned) == 0


def test_foreground_masker_classification_contact_sheet_and_session_reuse(tmp_path: Path) -> None:
    """Verify valid vs excluded classification, 4x4 masks_grid.jpg generation, and session cleanup."""
    images_dir = tmp_path / "dense" / "images"
    images_dir.mkdir(parents=True)
    masks_dir = tmp_path / "masks"
    debug_dir = tmp_path / "debug_masks"

    # 6 frames: 4 valid (~19.6%), 1 empty_or_tiny (0%), 1 over_segmented (100%) -> 4/6 = 66.7% >= 60%
    for idx in range(1, 7):
        img = np.full((100, 100, 3), 20 * idx, dtype=np.uint8)
        cv2.imwrite(str(images_dir / f"frame_{idx:04d}.jpg"), img)

    call_sessions: list[object] = []
    fake_session = object()

    def _mock_remove(img_rgb: np.ndarray, *, session: object, only_mask: bool = True) -> np.ndarray:
        assert only_mask is True
        call_sessions.append(session)
        val = int(round(float(img_rgb.mean())))
        out = np.zeros((100, 100), dtype=np.uint8)
        if val <= 85:  # frames 1..4: valid centered object
            cv2.circle(out, (50, 50), 25, 255, -1)
        elif val <= 105:  # frame 5: empty_or_tiny
            pass
        else:  # frame 6: over_segmented
            out[:, :] = 255
        return out

    masker = ForegroundMasker(session=fake_session, remove_fn=_mock_remove)
    result = masker.mask_directory(images_dir, masks_dir, debug_dir=debug_dir)

    assert result.total_frames == 6
    assert len(result.valid_views) == 4
    assert len(result.excluded_views) == 2
    assert all(s is fake_session for s in call_sessions)
    assert masker._session is None  # closed automatically

    reasons = {entry["filename"]: entry["reason"] for entry in result.excluded_views}
    assert reasons["frame_0005.jpg"] == "empty_or_tiny"
    assert reasons["frame_0006.jpg"] == "over_segmented"

    # Verify 4x4 visual contact sheet exists and is a valid JPEG image
    assert result.contact_sheet_path == (debug_dir / "masks_grid.jpg").resolve()
    assert result.contact_sheet_path.is_file()
    grid_img = cv2.imread(str(result.contact_sheet_path), cv2.IMREAD_COLOR)
    assert grid_img is not None
    assert grid_img.shape == (4 * 240, 4 * 320, 3)


def test_foreground_masker_circuit_breaker_below_20_valid_views(tmp_path: Path) -> None:
    """Verify circuit breaker raises RuntimeError when <20 valid views remain (and writes contact sheet)."""
    images_dir = tmp_path / "imgs"
    images_dir.mkdir()
    masks_dir = tmp_path / "masks"
    debug_dir = tmp_path / "debug_masks"

    # 22 total views: only 15 valid, 7 empty -> < 20 valid -> MUST abort with RuntimeError
    for idx in range(1, 23):
        val = 50 if idx <= 15 else 200
        cv2.imwrite(str(images_dir / f"f_{idx:04d}.jpg"), np.full((64, 64, 3), val, dtype=np.uint8))

    def _mock_remove(img_rgb: np.ndarray, *, session: object, only_mask: bool = True) -> np.ndarray:
        out = np.zeros((64, 64), dtype=np.uint8)
        if float(img_rgb.mean()) < 100:
            cv2.circle(out, (32, 32), 16, 255, -1)
        return out

    masker = ForegroundMasker(session=object(), remove_fn=_mock_remove)
    with pytest.raises(RuntimeError, match="circuit breaker triggered: only 15/22 valid views"):
        masker.mask_directory(images_dir, masks_dir, debug_dir=debug_dir)

    # Contact sheet must still be written so operator can diagnose why views failed
    assert (debug_dir / "masks_grid.jpg").is_file()


def test_foreground_masker_default_model_resume_and_onnx_session_options(tmp_path: Path) -> None:
    """Verify isnet-general-use default, bounded ONNX SessionOptions, and instant disk resume."""
    masker_default = ForegroundMasker()
    assert masker_default.model_name == "isnet-general-use"

    masker_lite = ForegroundMasker(model_name="birefnet-general-lite")
    assert masker_lite.model_name == "birefnet-general-lite"

    captured: dict[str, object] = {}

    def _fake_new_session(model_name: str, *, sess_opts: object, providers: list[str]) -> object:
        captured["model_name"] = model_name
        captured["sess_opts"] = sess_opts
        captured["providers"] = providers
        return MagicMock()

    with patch("rembg.new_session", side_effect=_fake_new_session):
        masker_default._ensure_session()

    assert captured["model_name"] == "isnet-general-use"
    assert captured["providers"] == ["CPUExecutionProvider"]
    sess_opts = captured["sess_opts"]
    assert sess_opts.enable_cpu_mem_arena is False
    assert sess_opts.enable_mem_pattern is False
    assert sess_opts.intra_op_num_threads == 4
    assert sess_opts.inter_op_num_threads == 1

    masker_default.close()
    assert masker_default._session is None

    # Verify existing mask PNGs are skipped on resume without invoking inference
    images_dir = tmp_path / "imgs"
    masks_dir = tmp_path / "masks"
    images_dir.mkdir()
    masks_dir.mkdir()

    for idx in (1, 2):
        cv2.imwrite(str(images_dir / f"f_{idx}.jpg"), np.full((64, 64, 3), 120, dtype=np.uint8))

    pre_mask = np.zeros((64, 64), dtype=np.uint8)
    cv2.circle(pre_mask, (32, 32), 16, 255, -1)
    cv2.imwrite(str(masks_dir / "f_1.png"), pre_mask)

    invocations = 0

    def _counting_remove(img_rgb: np.ndarray, *, session: object, only_mask: bool = True) -> np.ndarray:
        nonlocal invocations
        invocations += 1
        out = np.zeros((64, 64), dtype=np.uint8)
        cv2.circle(out, (32, 32), 16, 255, -1)
        return out

    resume_masker = ForegroundMasker(session=object(), remove_fn=_counting_remove)
    res = resume_masker.mask_directory(images_dir, masks_dir)
    assert res.total_frames == 2
    assert invocations == 1
