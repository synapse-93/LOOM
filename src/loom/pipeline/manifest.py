"""Typed pipeline execution manifest and cache-hygiene manager for LOOM."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import cv2

from loom.utils.paths import ensure_directory

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "pipeline_manifest.json"
FAST_HASH_CHUNK_BYTES = 1024 * 1024  # 1 MB head + 1 MB tail
STALE_WORKSPACE_DIRS: tuple[str, ...] = (
    "extracted_frames",
    "images",
    "sparse",
    "dense",
    "masks",
)
STALE_WORKSPACE_FILES: tuple[str, ...] = (
    "database.db",
    "database.db-wal",
    "database.db-shm",
)
IMAGE_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png"})


def compute_fast_video_sha256(video_path: Path | str) -> str:
    """Compute a fast deterministic SHA-256 over file size + first 1 MB + last 1 MB."""
    p = Path(video_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"Video file does not exist: {p}")

    size = p.stat().st_size
    hasher = hashlib.sha256()
    hasher.update(str(size).encode("ascii"))
    hasher.update(b":")

    with open(p, "rb") as f:
        head = f.read(FAST_HASH_CHUNK_BYTES)
        hasher.update(head)
        if size > FAST_HASH_CHUNK_BYTES:
            tail_offset = max(FAST_HASH_CHUNK_BYTES, size - FAST_HASH_CHUNK_BYTES)
            f.seek(tail_offset)
            tail = f.read(FAST_HASH_CHUNK_BYTES)
            hasher.update(tail)

    return hasher.hexdigest()


def detect_existing_frame_resolution(workspace: Path | str) -> tuple[int, int] | None:
    """Inspect existing extracted/workspace frames and return (width, height), or None."""
    ws = Path(workspace).resolve()
    for subdir in ("extracted_frames", "images"):
        d = ws / subdir
        if not d.is_dir():
            continue
        for candidate in sorted(d.iterdir()):
            if candidate.is_file() and candidate.suffix.lower() in IMAGE_EXTENSIONS:
                img = cv2.imread(str(candidate), cv2.IMREAD_COLOR)
                if img is not None and img.size > 0:
                    h, w = img.shape[:2]
                    return (int(w), int(h))
    return None


def wipe_stale_workspace_artifacts(workspace: Path | str) -> list[str]:
    """Remove stale reconstruction caches from workspace to prevent cross-run collisions."""
    ws = Path(workspace).resolve()
    removed: list[str] = []
    if not ws.is_dir():
        return removed

    for dirname in STALE_WORKSPACE_DIRS:
        target = ws / dirname
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
            removed.append(dirname)

    for filename in STALE_WORKSPACE_FILES:
        target = ws / filename
        if target.is_file():
            try:
                target.unlink()
                removed.append(filename)
            except OSError as exc:
                logger.warning("Could not remove stale file %s: %s", target, exc)

    for debug_entry in sorted(ws.glob("debug_*")):
        if debug_entry.is_dir():
            shutil.rmtree(debug_entry, ignore_errors=True)
            removed.append(debug_entry.name)
        elif debug_entry.is_file():
            try:
                debug_entry.unlink()
                removed.append(debug_entry.name)
            except OSError as exc:
                logger.warning("Could not remove stale debug file %s: %s", debug_entry, exc)

    return removed


@dataclass
class PipelineManifest:
    """Persistent execution manifest serialized to ``<workspace>/pipeline_manifest.json``."""

    video_path: str
    video_sha256: str
    engine: str
    turbo: bool
    max_frames: int | None = None
    frame_resolution: tuple[int, int] | None = None
    sfm: dict[str, Any] = field(default_factory=dict)
    masking: dict[str, Any] = field(default_factory=dict)
    visual_hull: dict[str, Any] = field(default_factory=dict)
    gaussian_2dgs: dict[str, Any] = field(default_factory=dict)
    tsdf: dict[str, Any] = field(default_factory=dict)
    export: dict[str, Any] = field(default_factory=dict)
    stages_completed: list[str] = field(default_factory=list)

    def mark_stage_complete(self, stage: str) -> None:
        """Record a completed pipeline stage idempotently."""
        if stage not in self.stages_completed:
            self.stages_completed.append(stage)

    def invalidate_from_stage(
        self,
        stage: str,
        stage_order: tuple[str, ...] = (
            "frames",
            "sfm",
            "undistort",
            "mask",
            "visual_hull",
            "2dgs",
            "tsdf",
            "export",
        ),
    ) -> None:
        """Remove ``stage`` and all downstream stages from ``stages_completed`` to force re-execution."""
        if stage not in stage_order:
            return
        cut_idx = stage_order.index(stage)
        to_drop = set(stage_order[cut_idx:])
        self.stages_completed = [s for s in self.stages_completed if s not in to_drop]
        if "visual_hull" in to_drop:
            self.visual_hull = {}
        if "2dgs" in to_drop:
            self.gaussian_2dgs = {}
        if "tsdf" in to_drop:
            self.tsdf = {}
        if "export" in to_drop:
            self.export = {}

    def is_stage_complete(self, stage: str) -> bool:
        """Return True if stage has already completed in this validated workspace."""
        return stage in self.stages_completed

    def to_dict(self) -> dict[str, Any]:
        return {
            "video_path": self.video_path,
            "video_sha256": self.video_sha256,
            "engine": self.engine,
            "turbo": self.turbo,
            "max_frames": int(self.max_frames) if self.max_frames is not None else None,
            "frame_resolution": list(self.frame_resolution) if self.frame_resolution is not None else None,
            "sfm": dict(self.sfm),
            "masking": dict(self.masking),
            "visual_hull": dict(self.visual_hull),
            "gaussian_2dgs": dict(self.gaussian_2dgs),
            "tsdf": dict(self.tsdf),
            "export": dict(self.export),
            "stages_completed": list(self.stages_completed),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PipelineManifest:
        raw_res = data.get("frame_resolution")
        frame_res: tuple[int, int] | None = None
        if isinstance(raw_res, (list, tuple)) and len(raw_res) == 2:
            frame_res = (int(raw_res[0]), int(raw_res[1]))
        raw_max_frames = data.get("max_frames")
        max_frames_val = int(raw_max_frames) if raw_max_frames is not None else None
        return cls(
            video_path=str(data.get("video_path", "")),
            video_sha256=str(data.get("video_sha256", "")),
            engine=str(data.get("engine", "2dgs")),
            turbo=bool(data.get("turbo", False)),
            max_frames=max_frames_val,
            frame_resolution=frame_res,
            sfm=dict(data.get("sfm") or {}),
            masking=dict(data.get("masking") or {}),
            visual_hull=dict(data.get("visual_hull") or {}),
            gaussian_2dgs=dict(data.get("gaussian_2dgs") or {}),
            tsdf=dict(data.get("tsdf") or {}),
            export=dict(data.get("export") or {}),
            stages_completed=[str(s) for s in (data.get("stages_completed") or [])],
        )

    def save(self, workspace: Path | str) -> Path:
        """Persist manifest atomically to ``<workspace>/pipeline_manifest.json``."""
        ws = ensure_directory(Path(workspace).resolve())
        dest = ws / MANIFEST_FILENAME
        tmp = ws / f".{MANIFEST_FILENAME}.tmp"
        tmp.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
        tmp.replace(dest)
        return dest

    @classmethod
    def load(cls, workspace: Path | str) -> Optional[PipelineManifest]:
        """Load manifest from ``<workspace>/pipeline_manifest.json`` if present and valid."""
        path = Path(workspace).resolve() / MANIFEST_FILENAME
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return None
            return cls.from_dict(payload)
        except Exception as exc:
            logger.warning("Failed to parse pipeline manifest %s: %s", path, exc)
            return None


def prepare_workspace(
    workspace: Path,
    video_path: Path,
    engine: str,
    turbo: bool,
    max_frames: int | None = None,
) -> PipelineManifest:
    """Validate workspace cache against video SHA-256, max_frames, and resolution, wiping stale data.

    Wipes ``extracted_frames/``, ``images/``, ``database.db``, ``sparse/``, ``dense/``,
    ``masks/``, and ``debug_*`` whenever:
      - ``pipeline_manifest.json`` does not exist,
      - ``video_sha256`` differs from the current video,
      - ``turbo`` mode changed (changing target keyframe resolution),
      - ``max_frames`` was supplied and differs from ``manifest.max_frames``, or
      - existing frames on disk do not match ``manifest.frame_resolution``.

    When the hash, keyframe budget, and resolution match, preserves existing artifacts and returns
    the loaded ``PipelineManifest`` so already-completed stages can safely resume.
    """
    ws = ensure_directory(Path(workspace).resolve())
    resolved_video = Path(video_path).resolve()
    video_sha = compute_fast_video_sha256(resolved_video)

    existing = PipelineManifest.load(ws)
    invalidation_reason: Optional[str] = None

    if existing is None:
        invalidation_reason = "missing pipeline_manifest.json"
    elif existing.video_sha256 != video_sha:
        invalidation_reason = (
            f"video_sha256 mismatch ({existing.video_sha256[:12]} != {video_sha[:12]})"
        )
    elif existing.turbo != bool(turbo):
        invalidation_reason = f"turbo preset changed ({existing.turbo} -> {bool(turbo)})"
    elif max_frames is not None and existing.max_frames != int(max_frames):
        invalidation_reason = f"max_frames changed ({existing.max_frames} -> {int(max_frames)})"
    else:
        disk_res = detect_existing_frame_resolution(ws)
        if (
            existing.frame_resolution is not None
            and disk_res is not None
            and disk_res != existing.frame_resolution
        ):
            invalidation_reason = (
                f"frame_resolution mismatch (manifest={existing.frame_resolution} vs disk={disk_res})"
            )

    if invalidation_reason is not None:
        purged = wipe_stale_workspace_artifacts(ws)
        logger.info(
            "[CACHE] Invalidating workspace '%s' (%s); purged=%s",
            ws,
            invalidation_reason,
            purged if purged else "none",
        )
        manifest = PipelineManifest(
            video_path=str(resolved_video),
            video_sha256=video_sha,
            engine=str(engine),
            turbo=bool(turbo),
            max_frames=int(max_frames) if max_frames is not None else None,
        )
        manifest.save(ws)
        return manifest

    assert existing is not None
    existing.video_path = str(resolved_video)
    existing.engine = str(engine)
    if max_frames is not None:
        existing.max_frames = int(max_frames)
    existing.save(ws)
    logger.info(
        "[CACHE] Resuming validated workspace '%s' (sha256=%s, stages_completed=%s)",
        ws,
        video_sha[:12],
        existing.stages_completed,
    )
    return existing

