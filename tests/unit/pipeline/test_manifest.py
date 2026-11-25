"""Unit tests for PipelineManifest and deterministic workspace cache hygiene."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from loom.pipeline.manifest import (
    MANIFEST_FILENAME,
    PipelineManifest,
    compute_fast_video_sha256,
    prepare_workspace,
)


def _seed_stale_workspace(ws: Path, frame_size: tuple[int, int] = (960, 540)) -> None:
    """Populate synthetic stale caches inside workspace."""
    w, h = frame_size
    (ws / "extracted_frames").mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ws / "extracted_frames" / "frame_0001.jpg"), np.zeros((h, w, 3), dtype=np.uint8))
    (ws / "images").mkdir(parents=True, exist_ok=True)
    (ws / "images" / "frame_0001.jpg").write_bytes(b"img")
    (ws / "database.db").write_bytes(b"sqlite-stale")
    (ws / "sparse" / "0").mkdir(parents=True, exist_ok=True)
    (ws / "sparse" / "0" / "cameras.bin").write_bytes(b"old-cam")
    (ws / "dense").mkdir(parents=True, exist_ok=True)
    (ws / "dense" / "fused.ply").write_bytes(b"ply")
    (ws / "masks").mkdir(parents=True, exist_ok=True)
    (ws / "masks" / "frame_0001.png").write_bytes(b"mask")
    (ws / "debug_2dgs").mkdir(parents=True, exist_ok=True)
    (ws / "debug_2dgs" / "view_0.png").write_bytes(b"dbg")


def test_prepare_workspace_wipes_stale_caches_on_missing_or_mismatched_sha(tmp_path: Path) -> None:
    """Verify missing manifest or changed video SHA-256 wipes stale sparse/, database.db, etc."""
    video_a = tmp_path / "video_a.mp4"
    video_b = tmp_path / "video_b.mp4"
    video_a.write_bytes(b"VIDEO_A_PAYLOAD" * 100)
    video_b.write_bytes(b"VIDEO_B_DIFFERENT_PAYLOAD" * 100)

    ws = tmp_path / "ws"
    _seed_stale_workspace(ws)

    # 1. Missing pipeline_manifest.json -> wipes all stale caches
    m1 = prepare_workspace(ws, video_a, engine="2dgs", turbo=True)
    assert isinstance(m1, PipelineManifest)
    assert (ws / MANIFEST_FILENAME).is_file()
    assert not (ws / "sparse").exists()
    assert not (ws / "database.db").exists()
    assert not (ws / "extracted_frames").exists()
    assert not (ws / "dense").exists()
    assert not (ws / "masks").exists()
    assert not (ws / "debug_2dgs").exists()
    assert m1.video_sha256 == compute_fast_video_sha256(video_a)

    # 2. Record completed stages + matching frame resolution -> resume cleanly on same video
    _seed_stale_workspace(ws, frame_size=(720, 405))
    m1.frame_resolution = (720, 405)
    m1.sfm = {"registered_views": 60, "total_views": 60, "num_cameras": 1}
    m1.mark_stage_complete("frames")
    m1.mark_stage_complete("sfm")
    m1.save(ws)

    m_resume = prepare_workspace(ws, video_a, engine="2dgs", turbo=True)
    assert m_resume.is_stage_complete("frames")
    assert m_resume.is_stage_complete("sfm")
    assert m_resume.sfm["num_cameras"] == 1
    assert (ws / "sparse" / "0" / "cameras.bin").is_file()
    assert (ws / "database.db").is_file()

    # 3. Different video SHA-256 -> wipes stale sparse/ and database.db cleanly
    m_changed = prepare_workspace(ws, video_b, engine="2dgs", turbo=True)
    assert m_changed.video_sha256 == compute_fast_video_sha256(video_b)
    assert m_changed.stages_completed == []
    assert not (ws / "sparse").exists()
    assert not (ws / "database.db").exists()


def test_prepare_workspace_wipes_on_frame_resolution_mismatch(tmp_path: Path) -> None:
    """Verify mismatched frame resolution on disk invalidates stale sparse cache."""
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"CLIP_DATA" * 50)
    ws = tmp_path / "ws_res"

    m = prepare_workspace(ws, video, engine="2dgs", turbo=False)
    m.frame_resolution = (960, 540)
    m.mark_stage_complete("frames")
    m.mark_stage_complete("sfm")
    m.save(ws)

    # Seed frames on disk with DIFFERENT resolution (1080x608 vs manifest 960x540)
    _seed_stale_workspace(ws, frame_size=(1080, 608))

    m2 = prepare_workspace(ws, video, engine="2dgs", turbo=False)
    assert m2.stages_completed == []
    assert not (ws / "sparse").exists()
    assert not (ws / "database.db").exists()


def test_prepare_workspace_invalidates_when_max_frames_changes(tmp_path: Path) -> None:
    """Verify changing max_frames (e.g. 75 -> 130) invalidates cached frames/sfm, while matching resumes."""
    video = tmp_path / "orbit.mp4"
    video.write_bytes(b"ORBIT_VIDEO_STREAM" * 40)
    ws = tmp_path / "ws_mf"

    m1 = prepare_workspace(ws, video, engine="2dgs", turbo=False, max_frames=75)
    assert m1.max_frames == 75
    _seed_stale_workspace(ws, frame_size=(960, 540))
    m1.frame_resolution = (960, 540)
    m1.mark_stage_complete("frames")
    m1.mark_stage_complete("sfm")
    m1.save(ws)

    # Matching max_frames=75 -> resumes cleanly
    m_same = prepare_workspace(ws, video, engine="2dgs", turbo=False, max_frames=75)
    assert m_same.is_stage_complete("frames")
    assert m_same.is_stage_complete("sfm")

    # Changed max_frames=130 -> wipes stale 75-frame cache and stores max_frames=130
    m_new = prepare_workspace(ws, video, engine="2dgs", turbo=False, max_frames=130)
    assert m_new.max_frames == 130
    assert m_new.stages_completed == []
    assert not (ws / "extracted_frames").exists()
    assert not (ws / "sparse").exists()

