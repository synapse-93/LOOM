"""Tests for configuration loading and validation."""

from __future__ import annotations

from pathlib import Path
from loom.config.loader import load_config
from loom.config.models import LoomConfig

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "configs"


def test_default_config_model() -> None:
    """Verify default LoomConfig initializes with expected defaults."""
    cfg = LoomConfig()
    assert cfg.name == "loom_default"
    assert cfg.reconstruction.backend == "meshroom"
    assert cfg.scaling.strategy == "aruco"
    assert cfg.scaling.marker_size_mm == 50.0
    assert cfg.printability.min_wall_thickness_mm == 1.2


def test_load_default_yaml() -> None:
    """Verify configs/default.yaml loads into a valid LoomConfig."""
    default_yaml = CONFIG_DIR / "default.yaml"
    assert default_yaml.is_file()
    cfg = load_config(default_yaml)
    assert cfg.name == "default_pipeline"
    assert cfg.reconstruction.quality == "medium"
    assert cfg.export.format == "stl"


def test_load_development_yaml() -> None:
    """Verify configs/development.yaml loads into a valid LoomConfig."""
    dev_yaml = CONFIG_DIR / "development.yaml"
    assert dev_yaml.is_file()
    cfg = load_config(dev_yaml)
    assert cfg.name == "development_pipeline"
    assert cfg.video.sample_interval == 2
    assert cfg.reconstruction.quality == "low"


def test_load_experiment_yaml() -> None:
    """Verify configs/experiment.yaml loads into a valid LoomConfig."""
    exp_yaml = CONFIG_DIR / "experiment.yaml"
    assert exp_yaml.is_file()
    cfg = load_config(exp_yaml)
    assert cfg.name == "experiment_benchmark"
    assert cfg.reconstruction.quality == "high"
    assert cfg.validation.tolerance_mm == 0.5


def test_load_capture_config_custom_fields(tmp_path: Path) -> None:
    """Verify CaptureConfig custom fields (such as min_texture_score) are parsed from YAML."""
    custom_yaml = tmp_path / "capture_test.yaml"
    custom_yaml.write_text(
        """
name: "capture_test"
capture:
  sharpness_threshold: 120.0
  min_texture_score: 25.0
""",
        encoding="utf-8",
    )
    cfg = load_config(custom_yaml)
    assert cfg.capture.sharpness_threshold == 120.0
    assert cfg.capture.min_texture_score == 25.0


def test_load_mesh_config_all_fields(tmp_path: Path) -> None:
    """Verify all 10 previously dropped MeshConfig fields are preserved from YAML."""
    mesh_yaml = tmp_path / "mesh_test.yaml"
    mesh_yaml.write_text(
        """
name: "mesh_test"
mesh:
  clean_outliers: false
  close_holes: false
  fill_holes: false
  max_hole_size: 15
  max_hole_edges: 45
  poisson_depth: 6
  target_face_count: 35000
  component_strategy: "keep_all"
  min_component_faces: 250
  min_component_ratio: 0.12
  remove_degenerate_faces: false
  remove_unreferenced_vertices: false
  remove_duplicate_faces: false
  unify_normals: false
  degenerate_area_threshold: 0.00001
""",
        encoding="utf-8",
    )
    cfg = load_config(mesh_yaml)
    m = cfg.mesh
    assert m.clean_outliers is False
    assert m.close_holes is False
    assert m.fill_holes is False
    assert m.max_hole_size == 15
    assert m.max_hole_edges == 45
    assert m.poisson_depth == 6
    assert m.target_face_count == 35000
    assert m.component_strategy == "keep_all"
    assert m.min_component_faces == 250
    assert m.min_component_ratio == 0.12
    assert m.remove_degenerate_faces is False
    assert m.remove_unreferenced_vertices is False
    assert m.remove_duplicate_faces is False
    assert m.unify_normals is False
    assert m.degenerate_area_threshold == 0.00001


def test_load_mesh_config_defaults_preserved(tmp_path: Path) -> None:
    """Verify default values are preserved when mesh fields are omitted in YAML."""
    minimal_yaml = tmp_path / "minimal.yaml"
    minimal_yaml.write_text(
        """
name: "minimal"
mesh:
  max_hole_size: 50
""",
        encoding="utf-8",
    )
    cfg = load_config(minimal_yaml)
    m = cfg.mesh
    assert m.max_hole_size == 50
    assert m.close_holes is True
    assert m.fill_holes is True
    assert m.component_strategy == "largest"
    assert m.unify_normals is True
    assert m.remove_degenerate_faces is True
    assert m.min_component_faces == 100
    assert m.target_face_count == 50000


def test_load_pointcloud_voxel_downsample_zero(tmp_path: Path) -> None:
    """Verify explicit voxel_downsample_size (including zero) is not lost."""
    pc_yaml = tmp_path / "pc_test.yaml"
    pc_yaml.write_text(
        """
name: "pc_test"
pointcloud:
  voxel_downsample_size: 0.0
""",
        encoding="utf-8",
    )
    cfg = load_config(pc_yaml)
    assert cfg.pointcloud.voxel_downsample_size == 0.0
