"""FastAPI application exposing LOOM's local RTX 4060 GPU reconstruction worker."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from loom.utils.subprocess import run_subprocess
from loom.web.manager import (
    InvalidVideoExtensionError,
    JobNotFoundError,
    JobNotReadyError,
    ReconstructionJobManager,
    UploadTooLargeError,
)
from loom.web.models import HealthResponse, JobCreateResponse, JobSummary

logger = logging.getLogger(__name__)

CORS_ALLOW_ORIGINS: list[str] = [
    "https://loomvidcapture.vercel.app",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
CORS_ALLOW_ORIGIN_REGEX: str = r"https://.*\.vercel\.app"


def _probe_gpu() -> tuple[Optional[str], Optional[int], Optional[int]]:
    """Probe local NVIDIA GPU name and VRAM via nvidia-smi."""
    try:
        res = run_subprocess(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            timeout=5,
            check=False,
            stream_output=False,
        )
        if res.returncode != 0 or not res.stdout.strip():
            return None, None, None
        first_line = res.stdout.strip().splitlines()[0]
        parts = [p.strip() for p in first_line.split(",")]
        if len(parts) >= 3:
            return parts[0], int(float(parts[1])), int(float(parts[2]))
    except Exception as exc:
        logger.debug("nvidia-smi probe failed: %s", exc)
    return None, None, None


def _probe_colmap() -> Optional[str]:
    """Probe host COLMAP binary version using CUDA-aware subprocess environment."""
    try:
        res = run_subprocess(
            ["colmap", "-h"],
            timeout=5,
            check=False,
            stream_output=False,
        )
        output = (res.stdout or res.stderr or "").strip()
        if res.returncode == 0 and output:
            return output.splitlines()[0].strip()
    except Exception as exc:
        logger.debug("colmap -h probe failed: %s", exc)
    return None


def create_app(job_manager: Optional[ReconstructionJobManager] = None) -> FastAPI:
    """Create and configure the FastAPI LOOM GPU Worker application."""
    manager = job_manager or ReconstructionJobManager()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        manager.start()
        try:
            yield
        finally:
            await manager.stop()

    application = FastAPI(
        title="LOOM GPU Worker",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.state.job_manager = manager

    application.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOW_ORIGINS,
        allow_origin_regex=CORS_ALLOW_ORIGIN_REGEX,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        gpu_info, colmap_version = await asyncio.gather(
            asyncio.to_thread(_probe_gpu),
            asyncio.to_thread(_probe_colmap),
        )
        gpu_name, vram_total, vram_free = gpu_info
        ready = colmap_version is not None
        return HealthResponse(
            status="ok" if ready else "degraded",
            gpu_name=gpu_name,
            vram_total_mib=vram_total,
            vram_free_mib=vram_free,
            colmap_version=colmap_version,
            active_job_id=manager.active_job_id,
            queue_depth=manager.queue_depth,
            ready=ready,
        )

    @application.post(
        "/api/reconstruct",
        response_model=JobCreateResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_reconstruction(
        file: UploadFile = File(...),
        target_length_mm: float = Form(200.0),
        turbo: bool = Form(True),
    ) -> JobCreateResponse:
        if target_length_mm <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="target_length_mm must be positive.",
            )
        try:
            return await manager.create_job(
                upload_file=file,
                target_length_mm=target_length_mm,
                turbo=turbo,
            )
        except InvalidVideoExtensionError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except UploadTooLargeError as exc:
            raise HTTPException(
                status_code=getattr(status, "HTTP_413_CONTENT_TOO_LARGE", 413),
                detail=str(exc),
            ) from exc

    @application.get("/api/jobs", response_model=list[JobSummary])
    async def list_jobs() -> list[JobSummary]:
        return manager.list_jobs()

    @application.get("/api/jobs/{job_id}", response_model=JobSummary)
    async def get_job(job_id: str) -> JobSummary:
        try:
            return manager.get_job(job_id)
        except JobNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @application.get("/api/jobs/{job_id}/stream")
    async def stream_job_logs(job_id: str) -> StreamingResponse:
        try:
            # Verify job exists before opening SSE stream
            manager.get_job(job_id)
        except JobNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

        return StreamingResponse(
            manager.subscribe(job_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @application.get("/api/jobs/{job_id}/stl")
    async def download_stl(job_id: str) -> FileResponse:
        try:
            stl_path = manager.get_stl_path(job_id)
        except JobNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except JobNotReadyError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

        return FileResponse(
            path=str(stl_path),
            media_type="application/octet-stream",
            filename=stl_path.name,
        )

    @application.get("/api/jobs/{job_id}/manifest")
    async def download_manifest(job_id: str) -> dict:
        try:
            return manager.get_manifest(job_id)
        except JobNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except JobNotReadyError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @application.delete("/api/jobs/{job_id}", response_model=JobSummary)
    async def delete_or_cancel_job(job_id: str) -> JobSummary:
        try:
            return await manager.cancel_job(job_id)
        except JobNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return application


app = create_app()
