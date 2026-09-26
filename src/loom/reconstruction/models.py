"""Data models for 3D photogrammetric reconstruction jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ReconstructionJobConfig:
    """Configuration passed to a ReconstructionEngine adapter."""

    workspace_dir: Path
    quality_preset: str = "medium"
    timeout_seconds: int = 1800
    camera_model: str = "pinhole"
    binary_path: Optional[Path] = None
    keep_workspace: bool = True
    additional_args: list[str] = field(default_factory=list)
    extra_params: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ReconstructionResult:
    """Standardized output produced by a ReconstructionEngine."""

    mesh_path: Optional[Path] = None
    point_cloud_path: Optional[Path] = None
    camera_poses_path: Optional[Path] = None
    success: bool = False
    backend_name: str = "unknown"
    execution_time_seconds: float = 0.0
    log_output: str = ""
    error_message: Optional[str] = None
    input_frames_count: int = 0
    registered_cameras_count: Optional[int] = None
    registration_ratio: Optional[float] = None
    point_count: Optional[int] = None

    @property
    def backend(self) -> str:
        """Alias for backend_name."""
        return self.backend_name
