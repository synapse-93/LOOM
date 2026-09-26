"""Typed artifact data models representing intermediate and terminal pipeline outputs."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class BaseArtifact:
    """Base class for all immutable pipeline artifacts."""

    stage_name: str
    created_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VideoArtifact(BaseArtifact):
    """Artifact representing an ingested and validated source video."""

    video_path: Path = field(default_factory=lambda: Path())
    duration_seconds: float = 0.0
    frame_count: int = 0
    resolution: tuple[int, int] = (0, 0)
    fps: float = 0.0


@dataclass(frozen=True)
class FrameSetArtifact(BaseArtifact):
    """Artifact representing a set of extracted video frames."""

    frames_dir: Path = field(default_factory=lambda: Path())
    frame_paths: list[Path] = field(default_factory=list)
    total_extracted: int = 0


@dataclass(frozen=True)
class CaptureAnalysisArtifact(BaseArtifact):
    """Artifact representing visual quality and coverage analysis of frames."""

    selected_frames: list[Path] = field(default_factory=list)
    rejected_frames: list[Path] = field(default_factory=list)
    average_sharpness: float = 0.0
    coverage_score: float = 0.0
    guidance_notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReconstructionArtifact(BaseArtifact):
    """Artifact representing raw photogrammetry output (mesh and camera trajectory)."""

    mesh_path: Optional[Path] = None
    sparse_reconstruction_path: Optional[Path] = None
    dense_point_cloud_path: Optional[Path] = None
    point_cloud_path: Optional[Path] = None
    camera_poses_path: Optional[Path] = None
    backend_name: str = "unknown"
    execution_time_seconds: float = 0.0


@dataclass(frozen=True)
class PointCloudArtifact(BaseArtifact):
    """Artifact representing a cleaned or filtered 3D point cloud."""

    point_cloud_path: Path = field(default_factory=lambda: Path())
    point_count: int = 0


@dataclass(frozen=True)
class MeshArtifact(BaseArtifact):
    """Artifact representing a processed 3D surface mesh."""

    mesh_path: Path = field(default_factory=lambda: Path())
    vertex_count: int = 0
    face_count: int = 0
    is_cleaned: bool = False


@dataclass(frozen=True)
class ScaledMeshArtifact(BaseArtifact):
    """Artifact representing a metrically scaled 3D mesh."""

    mesh_path: Path = field(default_factory=lambda: Path())
    scale_factor: float = 1.0
    units: str = "mm"
    marker_detected: bool = False


@dataclass(frozen=True)
class ValidationArtifact(BaseArtifact):
    """Artifact representing dimensional comparison against ground truth."""

    report_path: Path = field(default_factory=lambda: Path())
    absolute_error_mm: Optional[float] = None
    relative_error_pct: Optional[float] = None
    passed: bool = False


@dataclass(frozen=True)
class PrintabilityArtifact(BaseArtifact):
    """Artifact representing manufacturing readiness and 3D print check results."""

    report_path: Path = field(default_factory=lambda: Path())
    is_watertight: bool = False
    is_manifold: bool = False
    min_thickness_mm: Optional[float] = None
    printable: bool = False


@dataclass(frozen=True)
class ExportArtifact(BaseArtifact):
    """Artifact representing final exported manufacturing models and manifest."""

    stl_path: Path = field(default_factory=lambda: Path())
    manifest_path: Path = field(default_factory=lambda: Path())
    file_size_bytes: int = 0
