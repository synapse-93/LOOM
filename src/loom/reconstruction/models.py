"""Data models for 3D photogrammetric reconstruction jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class ReconstructionStatus(str, Enum):
    """Categorized execution status and failure classifications for 3D reconstruction."""

    SUCCESS = "success"
    PARTIAL = "partial"  # e.g., camera poses or point cloud generated, but mesh incomplete/missing
    BINARY_UNAVAILABLE = "binary_unavailable"
    INVALID_INPUT = "invalid_input"
    PROCESS_FAILED = "process_failed"
    TIMEOUT = "timeout"
    ARTIFACT_MISSING = "artifact_missing"


class ReconstructionStage(str, Enum):
    """Conceptual stages of the multi-view 3D reconstruction pipeline."""

    STAGE_0_INPUT_VALIDATION = "input_validation"
    STAGE_1_CAMERA_INIT = "camera_init_feature_matching"
    STAGE_2_CAMERA_REGISTRATION = "camera_registration_sfm"
    STAGE_3_SPARSE_RECONSTRUCTION = "sparse_reconstruction"
    STAGE_4_DENSE_RECONSTRUCTION = "dense_reconstruction_mvs"
    STAGE_5_MESH_GENERATION = "raw_mesh_generation"
    STAGE_6_ARTIFACT_DISCOVERY = "artifact_discovery"
    STAGE_7_DIAGNOSTICS = "diagnostics_report"


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

    success: bool = False
    status: ReconstructionStatus = ReconstructionStatus.SUCCESS
    backend_name: str = "unknown"
    mesh_path: Optional[Path] = None
    sparse_reconstruction_path: Optional[Path] = None
    dense_point_cloud_path: Optional[Path] = None
    point_cloud_path: Optional[Path] = None
    camera_poses_path: Optional[Path] = None
    execution_time_seconds: float = 0.0
    input_frames_count: int = 0
    registered_cameras_count: Optional[int] = None
    registration_ratio: Optional[float] = None
    point_count: Optional[int] = None
    workspace_dir: Optional[Path] = None
    output_dir: Optional[Path] = None
    log_path: Optional[Path] = None
    log_output: str = ""
    error_message: Optional[str] = None

    @property
    def backend(self) -> str:
        """Alias for backend_name."""
        return self.backend_name

    @property
    def raw_mesh_path(self) -> Optional[Path]:
        """Alias for mesh_path."""
        return self.mesh_path

    @property
    def workspace_path(self) -> Optional[Path]:
        """Alias for workspace_dir."""
        return self.workspace_dir

    @property
    def input_frame_count(self) -> int:
        """Alias for input_frames_count."""
        return self.input_frames_count

    @property
    def registered_camera_count(self) -> Optional[int]:
        """Alias for registered_cameras_count."""
        return self.registered_cameras_count
