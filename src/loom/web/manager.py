"""Single-GPU FIFO job manager with live SSE log fan-out for LOOM."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import sys
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Optional

from fastapi import UploadFile

from loom.utils.paths import ensure_directory
from loom.utils.subprocess import _build_subprocess_env
from loom.web.models import JobCreateResponse, JobStatus, JobSummary

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".mp4", ".webm", ".mov"})
MAX_UPLOAD_BYTES: int = 500 * 1024 * 1024  # 500 MB
UPLOAD_CHUNK_SIZE: int = 1024 * 1024  # 1 MB
MAX_LOG_LINES: int = 2000
HEARTBEAT_INTERVAL_SECONDS: float = 15.0
TERMINAL_STATUSES: frozenset[str] = frozenset({"COMPLETED", "FAILED", "CANCELLED"})


class InvalidVideoExtensionError(ValueError):
    """Raised when an uploaded video has an unsupported file extension or empty body."""


class UploadTooLargeError(ValueError):
    """Raised when an uploaded video exceeds the maximum permitted byte size."""


class JobNotFoundError(KeyError):
    """Raised when a requested job ID does not exist."""


class JobNotReadyError(RuntimeError):
    """Raised when an artifact is requested before the job has completed."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def infer_stage_and_progress(
    line: str,
    current_progress: int,
    current_stage: str,
) -> tuple[int, str]:
    """Infer monotonic progress (0-100) and human-readable stage from LOOM log output."""
    import re

    lower = line.lower()

    # Dynamic interpolation for [2DGS] Step <cur>/<total> (maps smoothly across 48%..78%)
    if "[2dgs]" in lower:
        m = re.search(r"step\s+(\d+)\s*/\s*(\d+)", lower)
        if m:
            cur_step = int(m.group(1))
            tot_steps = max(1, int(m.group(2)))
            frac = min(1.0, max(0.0, cur_step / float(tot_steps)))
            pct = 48 + int(round(frac * 30.0))
            label = f"Phase 4: Masked 2DGS Optimization ({cur_step}/{tot_steps})"
            if pct >= current_progress:
                return pct, label
            return current_progress, current_stage
        if current_progress < 48:
            return 48, "Phase 4: Masked 2DGS Optimization"
        return current_progress, current_stage

    stage_rules: tuple[tuple[tuple[str, ...], int, str], ...] = (
        (("[export] validated metric binary stl exported", "validated metric binary stl exported", "binary stl exported"), 99, "Phase 8: Binary STL Exported"),
        (("printabilitygate", "printability gate", "[export] running printabilitygate", "manufacturing readiness", "binary stl export"), 96, "Phase 8: Printability Gate & STL Export"),
        (("[export] quadric decimation", "target-length uniform scaling", "scaled mesh", "phase 4 metric scaling"), 93, "Phase 7: Metric Scaling & Build-Plate Snap"),
        (("[export] tier 2", "[export] tier 1", "[export] planar base cut", "base capping", "slice_and_cap_base", "mapbox-earcut"), 90, "Phase 6: Watertight Solidification & Base Cap"),
        (("[export] applied taubin", "[export] starting surface polish", "[export]", "phase 3 mesh cleaning", "starting phase 3", "mesh processing"), 86, "Phase 6: Surface Polish & Cleanup"),
        (("[tsdf] extracted raw 2dgs mesh", "poisson meshing succeeded", "delaunay mesher fallback succeeded"), 84, "Phase 5: Surface Mesh Extracted"),
        (("[tsdf]", "poisson_mesher", "delaunay_mesher"), 80, "Phase 5: TSDF Volumetric Fusion & Marching Cubes"),
        (("foreground segmentation",), 76, "Phase 4: Foreground Isolation"),
        (("support plane alignment", "canonical frame normalization", "canonical alignment"), 72, "Phase 4: Canonical Support Alignment"),
        (("stereo fusion point cloud",), 68, "Phase 3: Dense Point Cloud Fused"),
        (("stereo_fusion",), 64, "Phase 3: Stereo Fusion"),
        (("patch_match_stereo",), 52, "Phase 3: CUDA PatchMatch Stereo"),
        (("[visual_hull]",), 47, "Phase 3: Multi-View Visual-Hull Core"),
        (("[mask] completed",), 45, "Phase 3: Foreground Masking Complete"),
        (("[mask]",), 42, "Phase 3: Foreground Masking"),
        (("image_undistorter", "executing dense colmap"), 41, "Phase 3: Image Undistortion"),
        (("sfm registered",), 38, "Phase 2: Sparse SfM Verified"),
        (("colmap stage 'mapper'", "generating sparse sfm"), 34, "Phase 2: Sparse SfM Mapper"),
        (("sequential_matcher", "exhaustive_matcher"), 28, "Phase 2: GPU Feature Matching"),
        (("feature_extractor",), 22, "Phase 2: SIFT Feature Extraction"),
        (("extracted ", "frame extraction"), 15, "Phase 1: Keyframes Extracted"),
        (("remuxing .webm",), 6, "Phase 1: Remuxing WebM Capture"),
        (("mode:", "video2print:"), 5, "Phase 1: Video Ingest"),
    )

    for tokens, pct, label in stage_rules:
        if any(tok in lower for tok in tokens):
            if pct > current_progress:
                return pct, label
            if pct == current_progress and label != current_stage:
                return pct, label
            return current_progress, current_stage

    return current_progress, current_stage


@dataclass
class _JobRecord:
    """Mutable internal runtime record for a single reconstruction job."""

    job_id: str
    filename: str
    job_dir: Path
    video_path: Path
    target_length_mm: float
    turbo: bool
    status: JobStatus = "QUEUED"
    progress: int = 0
    current_stage: str = "Queued"
    created_at: str = field(default_factory=_utc_now_iso)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    stl_path: Optional[Path] = None
    manifest_path: Optional[Path] = None
    manifest: Optional[dict[str, Any]] = None
    logs: deque[tuple[int, str]] = field(default_factory=lambda: deque(maxlen=MAX_LOG_LINES))
    next_seq: int = 0
    subscribers: list[asyncio.Queue[Optional[dict[str, Any]]]] = field(default_factory=list)
    process: Optional[Any] = None
    cancelled: bool = False

    def to_summary(self) -> JobSummary:
        stl_ready = (
            self.status == "COMPLETED"
            and self.stl_path is not None
            and self.stl_path.is_file()
        )
        return JobSummary(
            job_id=self.job_id,
            filename=self.filename,
            status=self.status,
            progress=self.progress,
            current_stage=self.current_stage,
            target_length_mm=self.target_length_mm,
            turbo=self.turbo,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
            error=self.error,
            stl_ready=stl_ready,
            manifest=self.manifest,
        )


class ReconstructionJobManager:
    """Single-GPU serialized FIFO reconstruction worker and SSE broadcaster."""

    def __init__(
        self,
        jobs_root: Optional[Path] = None,
        repo_root: Optional[Path] = None,
        subprocess_factory: Optional[Callable[..., Awaitable[Any]]] = None,
        max_upload_bytes: int = MAX_UPLOAD_BYTES,
        heartbeat_interval: float = HEARTBEAT_INTERVAL_SECONDS,
    ) -> None:
        self.repo_root: Path = (
            Path(repo_root).resolve()
            if repo_root is not None
            else Path(__file__).resolve().parents[3]
        )
        self.jobs_root: Path = (
            Path(jobs_root).resolve()
            if jobs_root is not None
            else (self.repo_root / "outputs" / "web_jobs").resolve()
        )
        self._subprocess_factory: Callable[..., Awaitable[Any]] = (
            subprocess_factory or asyncio.create_subprocess_exec
        )
        self.max_upload_bytes: int = max_upload_bytes
        self.heartbeat_interval: float = heartbeat_interval

        self._jobs: dict[str, _JobRecord] = {}
        self._pending_order: list[str] = []
        self._queue: Optional[asyncio.Queue[str]] = None
        self._worker_task: Optional[asyncio.Task[None]] = None
        self._active_job_id: Optional[str] = None

    @property
    def active_job_id(self) -> Optional[str]:
        return self._active_job_id

    @property
    def queue_depth(self) -> int:
        return sum(1 for r in self._jobs.values() if r.status == "QUEUED")

    def start(self) -> None:
        """Start the single-GPU FIFO worker task on the active event loop."""
        if self._queue is None:
            self._queue = asyncio.Queue()
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker_loop(), name="loom-gpu-worker")

    async def stop(self) -> None:
        """Gracefully terminate active subprocesses and stop the background worker."""
        if self._active_job_id and self._active_job_id in self._jobs:
            active_rec = self._jobs[self._active_job_id]
            active_rec.cancelled = True
            await self._terminate_process(active_rec)

        if self._worker_task is not None and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        self._worker_task = None
        self._active_job_id = None

    async def create_job(
        self,
        upload_file: UploadFile,
        target_length_mm: float = 200.0,
        turbo: bool = True,
    ) -> JobCreateResponse:
        """Validate, stream-ingest, and enqueue a video reconstruction job."""
        original_name = Path(upload_file.filename or "upload.mp4").name
        ext = Path(original_name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise InvalidVideoExtensionError(
                f"Unsupported video extension '{ext}'. Allowed extensions: {sorted(ALLOWED_EXTENSIONS)}"
            )

        job_id = uuid.uuid4().hex[:12]
        job_dir = ensure_directory(self.jobs_root / job_id)
        dest_path = job_dir / f"input{ext}"

        total_bytes = 0
        try:
            with open(dest_path, "wb") as out_f:
                while True:
                    chunk = await upload_file.read(UPLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > self.max_upload_bytes:
                        raise UploadTooLargeError(
                            f"Upload exceeds maximum allowed size of {self.max_upload_bytes // (1024 * 1024)} MB."
                        )
                    out_f.write(chunk)
            if total_bytes == 0:
                raise InvalidVideoExtensionError("Uploaded video file is empty.")
        except Exception:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise
        finally:
            await upload_file.close()

        record = _JobRecord(
            job_id=job_id,
            filename=original_name,
            job_dir=job_dir,
            video_path=dest_path,
            target_length_mm=float(target_length_mm),
            turbo=bool(turbo),
        )
        self._jobs[job_id] = record
        self._pending_order.append(job_id)

        self.start()
        assert self._queue is not None
        await self._queue.put(job_id)

        # Queue position: 1 means next/running immediately, >1 means waiting behind active/queued jobs
        ahead = (1 if self._active_job_id is not None else 0) + sum(
            1 for jid in self._pending_order if jid != job_id and self._jobs.get(jid) and self._jobs[jid].status == "QUEUED"
        )
        queue_position = ahead + 1

        return JobCreateResponse(
            job_id=job_id,
            status=record.status,
            queue_position=queue_position,
            stream_url=f"/api/jobs/{job_id}/stream",
            stl_url=f"/api/jobs/{job_id}/stl",
            manifest_url=f"/api/jobs/{job_id}/manifest",
        )

    def list_jobs(self) -> list[JobSummary]:
        """Return all job summaries sorted newest first."""
        ordered = sorted(self._jobs.values(), key=lambda r: r.created_at, reverse=True)
        return [r.to_summary() for r in ordered]

    def get_job(self, job_id: str) -> JobSummary:
        record = self._get_record(job_id)
        return record.to_summary()

    def get_stl_path(self, job_id: str) -> Path:
        record = self._get_record(job_id)
        if record.status != "COMPLETED":
            raise JobNotReadyError(f"Job '{job_id}' is not completed (current status: {record.status}).")
        if record.stl_path is None or not record.stl_path.is_file():
            raise FileNotFoundError(f"STL artifact missing for job '{job_id}'.")
        return record.stl_path

    def get_manifest(self, job_id: str) -> dict[str, Any]:
        record = self._get_record(job_id)
        if record.status != "COMPLETED":
            raise JobNotReadyError(f"Job '{job_id}' is not completed (current status: {record.status}).")
        if record.manifest is not None:
            return record.manifest
        if record.manifest_path is not None and record.manifest_path.is_file():
            data = json.loads(record.manifest_path.read_text(encoding="utf-8"))
            record.manifest = data
            return data
        raise FileNotFoundError(f"Manifest artifact missing for job '{job_id}'.")

    async def cancel_job(self, job_id: str) -> JobSummary:
        """Cancel a queued/running job or remove a terminal job record."""
        record = self._get_record(job_id)

        if record.status == "QUEUED":
            record.cancelled = True
            record.status = "CANCELLED"
            record.current_stage = "Cancelled"
            record.completed_at = _utc_now_iso()
            self._append_log(record, "[WORKER] Job cancelled while queued.")
            self._broadcast_done(record)
            return record.to_summary()

        if record.status == "RUNNING":
            record.cancelled = True
            self._append_log(record, "[WORKER] Cancellation requested; terminating active subprocess...")
            await self._terminate_process(record)
            record.status = "CANCELLED"
            record.current_stage = "Cancelled"
            if record.completed_at is None:
                record.completed_at = _utc_now_iso()
            self._broadcast_done(record)
            return record.to_summary()

        # Terminal record: remove from registry and return last summary
        summary = record.to_summary()
        self._jobs.pop(job_id, None)
        return summary

    async def subscribe(self, job_id: str) -> AsyncIterator[str]:
        """Yield Server-Sent Events (log replay, live logs, progress, heartbeat, done)."""
        record = self._get_record(job_id)
        sub_q: asyncio.Queue[Optional[dict[str, Any]]] = asyncio.Queue()
        record.subscribers.append(sub_q)

        try:
            buffered = list(record.logs)
            last_seq = buffered[-1][0] if buffered else -1

            for seq, line in buffered:
                yield self._format_sse("log", {"seq": seq, "line": line})

            yield self._format_sse(
                "progress",
                {
                    "status": record.status,
                    "progress": record.progress,
                    "stage": record.current_stage,
                },
            )

            if record.status in TERMINAL_STATUSES:
                yield self._format_sse("done", record.to_summary().model_dump())
                return

            while True:
                try:
                    event = await asyncio.wait_for(sub_q.get(), timeout=self.heartbeat_interval)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue

                if event is None:
                    break

                ev_type = event["type"]
                if ev_type == "log":
                    if event["seq"] <= last_seq:
                        continue
                    last_seq = event["seq"]
                    yield self._format_sse("log", {"seq": event["seq"], "line": event["line"]})
                elif ev_type == "progress":
                    yield self._format_sse(
                        "progress",
                        {
                            "status": event["status"],
                            "progress": event["progress"],
                            "stage": event["stage"],
                        },
                    )
                elif ev_type == "done":
                    yield self._format_sse("done", event["payload"])
                    break
        finally:
            if sub_q in record.subscribers:
                record.subscribers.remove(sub_q)

    # ------------------------------------------------------------------
    # Internal Worker Loop & Helpers
    # ------------------------------------------------------------------

    def _get_record(self, job_id: str) -> _JobRecord:
        record = self._jobs.get(job_id)
        if record is None:
            raise JobNotFoundError(f"Job '{job_id}' not found.")
        return record

    @staticmethod
    def _format_sse(event_name: str, payload: dict[str, Any]) -> str:
        return f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"

    def _append_log(self, record: _JobRecord, line: str) -> None:
        seq = record.next_seq
        record.next_seq += 1
        record.logs.append((seq, line))
        self._broadcast(record, {"type": "log", "seq": seq, "line": line})

    def _broadcast(self, record: _JobRecord, event: Optional[dict[str, Any]]) -> None:
        for q in list(record.subscribers):
            q.put_nowait(event)

    def _broadcast_done(self, record: _JobRecord) -> None:
        self._broadcast(record, {"type": "done", "payload": record.to_summary().model_dump()})
        self._broadcast(record, None)

    async def _terminate_process(self, record: _JobRecord) -> None:
        proc = record.process
        if proc is None:
            return
        if getattr(proc, "returncode", None) is not None:
            return
        try:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        except ProcessLookupError:
            pass
        except Exception as exc:
            logger.warning("Error while terminating subprocess for job %s: %s", record.job_id, exc)

    async def _worker_loop(self) -> None:
        assert self._queue is not None
        while True:
            job_id = await self._queue.get()
            try:
                if job_id in self._pending_order:
                    self._pending_order.remove(job_id)
                record = self._jobs.get(job_id)
                if record is None or record.cancelled or record.status in TERMINAL_STATUSES:
                    continue
                self._active_job_id = job_id
                await self._execute_job(record)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Unhandled worker error for job %s: %s", job_id, exc)
                record = self._jobs.get(job_id)
                if record is not None and record.status not in TERMINAL_STATUSES:
                    record.status = "FAILED"
                    record.current_stage = "Failed"
                    record.error = str(exc)
                    record.completed_at = _utc_now_iso()
                    self._broadcast_done(record)
            finally:
                self._active_job_id = None
                self._queue.task_done()

    async def _maybe_remux_webm(self, record: _JobRecord) -> Path:
        if record.video_path.suffix.lower() != ".webm":
            return record.video_path

        ffmpeg_bin = shutil.which("ffmpeg")
        if ffmpeg_bin is None:
            msg = "[WARNING] ffmpeg not found on PATH; passing .webm directly to OpenCV ingest."
            logger.warning(msg)
            self._append_log(record, msg)
            return record.video_path

        remuxed_path = record.job_dir / "input_remuxed.mp4"
        self._append_log(record, f"[WORKER] Remuxing .webm capture via ffmpeg -> {remuxed_path.name}")
        proc = await self._subprocess_factory(
            ffmpeg_bin,
            "-y",
            "-i",
            str(record.video_path),
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-an",
            str(remuxed_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(record.job_dir),
            env=_build_subprocess_env(),
        )
        record.process = proc
        if proc.stdout is not None:
            while True:
                raw = await proc.stdout.readline()
                if not raw:
                    break
                text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if text:
                    self._append_log(record, f"[ffmpeg] {text}")
        rc = await proc.wait()
        record.process = None

        if rc == 0 and remuxed_path.is_file() and remuxed_path.stat().st_size > 0:
            self._append_log(record, "[WORKER] WebM remux complete.")
            return remuxed_path

        self._append_log(
            record,
            f"[WARNING] ffmpeg remux exited with code {rc}; falling back to original .webm input.",
        )
        return record.video_path

    async def _execute_job(self, record: _JobRecord) -> None:
        record.status = "RUNNING"
        record.started_at = _utc_now_iso()
        record.progress = 2
        record.current_stage = "Starting LOOM GPU reconstruction"
        self._broadcast(
            record,
            {"type": "progress", "status": record.status, "progress": record.progress, "stage": record.current_stage},
        )

        effective_video = await self._maybe_remux_webm(record)
        if record.cancelled:
            record.status = "CANCELLED"
            record.current_stage = "Cancelled"
            record.completed_at = _utc_now_iso()
            self._broadcast_done(record)
            return

        demo_script = self.repo_root / "scripts" / "demo.py"
        cmd: list[str] = [
            sys.executable,
            "-u",
            str(demo_script),
            "--video",
            str(effective_video),
            "--engine",
            "2dgs",
            "--output-dir",
            str(record.job_dir),
            "--target-length",
            str(record.target_length_mm),
            "--export-stl",
        ]
        if record.turbo:
            cmd.append("--turbo")

        self._append_log(record, f"[WORKER] Spawning pipeline: {' '.join(cmd)}")
        proc = await self._subprocess_factory(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(self.repo_root),
            env=_build_subprocess_env(),
        )
        record.process = proc

        if proc.stdout is not None:
            while True:
                raw = await proc.stdout.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                self._append_log(record, line)
                new_progress, new_stage = infer_stage_and_progress(
                    line, record.progress, record.current_stage
                )
                if new_progress != record.progress or new_stage != record.current_stage:
                    record.progress = new_progress
                    record.current_stage = new_stage
                    self._broadcast(
                        record,
                        {
                            "type": "progress",
                            "status": record.status,
                            "progress": record.progress,
                            "stage": record.current_stage,
                        },
                    )

        returncode = await proc.wait()
        record.process = None

        if record.cancelled:
            record.status = "CANCELLED"
            record.current_stage = "Cancelled"
            if record.completed_at is None:
                record.completed_at = _utc_now_iso()
            self._broadcast_done(record)
            return

        if returncode == 0:
            stl_path, manifest_path = self._discover_artifacts(record.job_dir)
            if stl_path is not None and stl_path.is_file() and stl_path.stat().st_size > 0:
                record.stl_path = stl_path
                record.manifest_path = manifest_path
                if manifest_path is not None and manifest_path.is_file():
                    try:
                        record.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    except Exception as exc:
                        logger.warning("Failed to parse manifest JSON %s: %s", manifest_path, exc)
                record.status = "COMPLETED"
                record.progress = 100
                record.current_stage = "Completed"
                record.completed_at = _utc_now_iso()
            else:
                record.status = "FAILED"
                record.current_stage = "Failed"
                record.error = "Reconstruction exited 0 but no binary STL artifact was found in job directory."
                record.completed_at = _utc_now_iso()
        else:
            tail_lines = [line for _, line in list(record.logs)[-15:]]
            record.status = "FAILED"
            record.current_stage = "Failed"
            record.error = "\n".join(tail_lines) if tail_lines else f"Pipeline exited with code {returncode}"
            record.completed_at = _utc_now_iso()

        self._broadcast_done(record)

    @staticmethod
    def _discover_artifacts(job_dir: Path) -> tuple[Optional[Path], Optional[Path]]:
        """Locate the generated binary STL (preferring loom_output.stl) and printability manifest."""
        preferred_stl = job_dir / "loom_output.stl"
        if preferred_stl.is_file() and preferred_stl.stat().st_size > 0:
            stl_path: Optional[Path] = preferred_stl
        else:
            stl_candidates = sorted(
                job_dir.rglob("*.stl"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            stl_path = stl_candidates[0] if stl_candidates else None

        preferred_manifest = job_dir / "printability_manifest.json"
        if preferred_manifest.is_file():
            manifest_path: Optional[Path] = preferred_manifest
        else:
            manifest_candidates = sorted(
                (p for p in job_dir.rglob("*_manifest.json") if p.name != "pipeline_manifest.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            manifest_path = manifest_candidates[0] if manifest_candidates else None
        return stl_path, manifest_path

