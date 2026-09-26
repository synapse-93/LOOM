"""Typed configuration data models for the LOOM pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class VideoConfig:
    """Settings for video ingest and frame extraction."""

    sample_interval: int = 1
    max_frames: int = 300
    target_fps: Optional[float] = None
    min_resolution_width: int = 1280
    min_resolution_height: int = 720
    jpeg_quality: int = 95


@dataclass
class CaptureConfig:
    """Settings for frame quality and coverage evaluation."""

    sharpness_threshold: float = 100.0
    max_blur_ratio: float = 0.3
    min_overlap_ratio: float = 0.6
    enable_coverage_estimation: bool = True
    min_brightness: float = 30.0
    max_brightness: float = 235.0
    min_contrast: float = 15.0
    redundancy_threshold: float = 0.98


@dataclass
class ReconstructionConfig:
    """Settings for external 3D reconstruction engine."""

    backend: str = "meshroom"  # Options: 'meshroom', 'colmap'
    quality: str = "medium"    # Options: 'low', 'medium', 'high'
    timeout_seconds: int = 1800
    workspace_dir: Optional[Path] = None


@dataclass
class PointCloudConfig:
    """Settings for point cloud cleaning and filtering."""

    clean_outliers: bool = True
    nb_neighbors: int = 20
    std_ratio: float = 2.0
    voxel_downsample_size: Optional[float] = None


@dataclass
class MeshConfig:
    """Settings for mesh repair and surface reconstruction."""

    clean_outliers: bool = True
    close_holes: bool = True
    max_hole_size: int = 30
    poisson_depth: int = 8
    target_face_count: Optional[int] = 50000


@dataclass
class ScalingConfig:
    """Settings for fiducial metric scaling."""

    strategy: str = "aruco"  # Options: 'aruco', 'manual'
    marker_id: int = 0
    marker_size_mm: float = 50.0
    dictionary: str = "DICT_4X4_50"


@dataclass
class ValidationConfig:
    """Settings for geometry and dimensional validation."""

    tolerance_mm: float = 1.0
    compute_hausdorff: bool = False
    ground_truth_dimensions_mm: Optional[tuple[float, float, float]] = None


@dataclass
class PrintabilityConfig:
    """Settings for 3D printability analysis."""

    check_manifold: bool = True
    check_watertight: bool = True
    min_wall_thickness_mm: float = 1.2
    max_overhang_angle_deg: float = 45.0
    target_bed_size_mm: tuple[float, float, float] = (220.0, 220.0, 250.0)


@dataclass
class ExportConfig:
    """Settings for model export and manifest generation."""

    format: str = "stl"
    output_dir: Path = field(default_factory=lambda: Path("outputs/stl"))
    binary: bool = True
    generate_manifest: bool = True


@dataclass
class LoomConfig:
    """Root configuration container for complete LOOM pipeline."""

    name: str = "loom_default"
    input_video: Optional[Path] = None
    output_dir: Path = field(default_factory=lambda: Path("outputs"))
    video: VideoConfig = field(default_factory=VideoConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    reconstruction: ReconstructionConfig = field(default_factory=ReconstructionConfig)
    pointcloud: PointCloudConfig = field(default_factory=PointCloudConfig)
    mesh: MeshConfig = field(default_factory=MeshConfig)
    scaling: ScalingConfig = field(default_factory=ScalingConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    printability: PrintabilityConfig = field(default_factory=PrintabilityConfig)
    export: ExportConfig = field(default_factory=ExportConfig)
