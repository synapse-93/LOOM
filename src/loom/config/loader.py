"""Configuration loader and serializer for LOOM YAML files."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Union
import yaml

from loom.config.models import (
    CaptureConfig,
    ExportConfig,
    LoomConfig,
    MeshConfig,
    PointCloudConfig,
    PrintabilityConfig,
    ReconstructionConfig,
    ScalingConfig,
    ValidationConfig,
    VideoConfig,
)
from loom.utils.paths import resolve_path


def _parse_dict_to_config(data: dict[str, Any]) -> LoomConfig:
    """Recursively map raw dictionary keys to LoomConfig dataclasses."""
    config = LoomConfig()

    if "name" in data:
        config.name = str(data["name"])
    if "input_video" in data and data["input_video"]:
        config.input_video = Path(data["input_video"])
    if "output_dir" in data and data["output_dir"]:
        config.output_dir = Path(data["output_dir"])

    if "video" in data and isinstance(data["video"], dict):
        v = data["video"]
        config.video = VideoConfig(
            sample_interval=int(v.get("sample_interval", config.video.sample_interval)),
            max_frames=int(v.get("max_frames", config.video.max_frames)),
            target_fps=float(v["target_fps"]) if v.get("target_fps") is not None else None,
            min_resolution_width=int(v.get("min_resolution_width", config.video.min_resolution_width)),
            min_resolution_height=int(v.get("min_resolution_height", config.video.min_resolution_height)),
            jpeg_quality=int(v.get("jpeg_quality", config.video.jpeg_quality)),
        )

    if "capture" in data and isinstance(data["capture"], dict):
        c = data["capture"]
        config.capture = CaptureConfig(
            sharpness_threshold=float(c.get("sharpness_threshold", config.capture.sharpness_threshold)),
            max_blur_ratio=float(c.get("max_blur_ratio", config.capture.max_blur_ratio)),
            min_overlap_ratio=float(c.get("min_overlap_ratio", config.capture.min_overlap_ratio)),
            enable_coverage_estimation=bool(c.get("enable_coverage_estimation", config.capture.enable_coverage_estimation)),
            min_brightness=float(c.get("min_brightness", config.capture.min_brightness)),
            max_brightness=float(c.get("max_brightness", config.capture.max_brightness)),
            min_contrast=float(c.get("min_contrast", config.capture.min_contrast)),
            redundancy_threshold=float(c.get("redundancy_threshold", config.capture.redundancy_threshold)),
        )

    if "reconstruction" in data and isinstance(data["reconstruction"], dict):
        r = data["reconstruction"]
        config.reconstruction = ReconstructionConfig(
            backend=str(r.get("backend", config.reconstruction.backend)),
            binary_path=Path(r["binary_path"]) if r.get("binary_path") else None,
            quality=str(r.get("quality", config.reconstruction.quality)),
            timeout_seconds=int(r.get("timeout_seconds", config.reconstruction.timeout_seconds)),
            workspace_dir=Path(r["workspace_dir"]) if r.get("workspace_dir") else None,
            keep_workspace=bool(r.get("keep_workspace", config.reconstruction.keep_workspace)),
            additional_args=list(r.get("additional_args", config.reconstruction.additional_args)),
        )

    if "pointcloud" in data and isinstance(data["pointcloud"], dict):
        p = data["pointcloud"]
        config.pointcloud = PointCloudConfig(
            clean_outliers=bool(p.get("clean_outliers", config.pointcloud.clean_outliers)),
            nb_neighbors=int(p.get("nb_neighbors", config.pointcloud.nb_neighbors)),
            std_ratio=float(p.get("std_ratio", config.pointcloud.std_ratio)),
            voxel_downsample_size=float(p["voxel_downsample_size"]) if p.get("voxel_downsample_size") else None,
        )

    if "mesh" in data and isinstance(data["mesh"], dict):
        m = data["mesh"]
        config.mesh = MeshConfig(
            clean_outliers=bool(m.get("clean_outliers", config.mesh.clean_outliers)),
            close_holes=bool(m.get("close_holes", config.mesh.close_holes)),
            max_hole_size=int(m.get("max_hole_size", config.mesh.max_hole_size)),
            poisson_depth=int(m.get("poisson_depth", config.mesh.poisson_depth)),
            target_face_count=int(m["target_face_count"]) if m.get("target_face_count") else None,
        )

    if "scaling" in data and isinstance(data["scaling"], dict):
        s = data["scaling"]
        config.scaling = ScalingConfig(
            strategy=str(s.get("strategy", config.scaling.strategy)),
            marker_id=int(s.get("marker_id", config.scaling.marker_id)),
            marker_size_mm=float(s.get("marker_size_mm", config.scaling.marker_size_mm)),
            dictionary=str(s.get("dictionary", config.scaling.dictionary)),
        )

    if "validation" in data and isinstance(data["validation"], dict):
        val = data["validation"]
        gt_dim = tuple(val["ground_truth_dimensions_mm"]) if val.get("ground_truth_dimensions_mm") else None
        config.validation = ValidationConfig(
            tolerance_mm=float(val.get("tolerance_mm", config.validation.tolerance_mm)),
            compute_hausdorff=bool(val.get("compute_hausdorff", config.validation.compute_hausdorff)),
            ground_truth_dimensions_mm=gt_dim,
        )

    if "printability" in data and isinstance(data["printability"], dict):
        pr = data["printability"]
        bed_size = tuple(pr.get("target_bed_size_mm", config.printability.target_bed_size_mm))
        config.printability = PrintabilityConfig(
            check_manifold=bool(pr.get("check_manifold", config.printability.check_manifold)),
            check_watertight=bool(pr.get("check_watertight", config.printability.check_watertight)),
            min_wall_thickness_mm=float(pr.get("min_wall_thickness_mm", config.printability.min_wall_thickness_mm)),
            max_overhang_angle_deg=float(pr.get("max_overhang_angle_deg", config.printability.max_overhang_angle_deg)),
            target_bed_size_mm=bed_size,
        )

    if "export" in data and isinstance(data["export"], dict):
        e = data["export"]
        config.export = ExportConfig(
            format=str(e.get("format", config.export.format)),
            output_dir=Path(e.get("output_dir", config.export.output_dir)),
            binary=bool(e.get("binary", config.export.binary)),
            generate_manifest=bool(e.get("generate_manifest", config.export.generate_manifest)),
        )

    return config


def load_config(path: Union[str, Path]) -> LoomConfig:
    """Load configuration from a YAML file.

    Args:
        path: Path to the YAML file.

    Returns:
        Populated LoomConfig instance.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        ValueError: If the YAML content is invalid or malformed.
    """
    config_path = resolve_path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"YAML configuration root must be a mapping, got {type(data).__name__}")

    return _parse_dict_to_config(data)
