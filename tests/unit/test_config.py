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
