"""Typed Pydantic response and state models for the LOOM FastAPI GPU worker."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

JobStatus = Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]


class HealthResponse(BaseModel):
    """Hardware, COLMAP toolchain, and queue readiness snapshot."""

    status: str
    gpu_name: Optional[str] = None
    vram_total_mib: Optional[int] = None
    vram_free_mib: Optional[int] = None
    colmap_version: Optional[str] = None
    active_job_id: Optional[str] = None
    queue_depth: int = 0
    ready: bool


class JobCreateResponse(BaseModel):
    """Response returned when a video reconstruction job is enqueued."""

    job_id: str
    status: JobStatus
    queue_position: int
    stream_url: str
    stl_url: str
    manifest_url: str


class JobSummary(BaseModel):
    """Full status snapshot for a queued, active, or completed job."""

    job_id: str
    filename: str
    status: JobStatus
    progress: int = Field(default=0, ge=0, le=100)
    current_stage: str
    target_length_mm: float
    turbo: bool
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    stl_ready: bool = False
    manifest: Optional[dict[str, Any]] = None

