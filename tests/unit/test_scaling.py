import os
import pytest
import trimesh
import numpy as np
from src.loom.scaling import MetricScalingProcessor, ScaleConfig

def test_metric_scaling_math():
    """Verifies that a 1x1x1 mesh scales to 2x2x2 when scale factor is 2.0."""
    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    
    # Physical size = 50mm, Reconstructed size = 25 units -> Scale factor = 2.0
    config = ScaleConfig(marker_size_mm=50.0)
    processor = MetricScalingProcessor(config)
    
    scaled_mesh, result = processor.process(mesh, reconstructed_marker_size=25.0)
    
    assert result.success is True
    assert result.scale_factor == 2.0
    np.testing.assert_allclose(scaled_mesh.extents, (2.0, 2.0, 2.0))

def test_scaling_json_report_export(tmp_path):
    """Verifies JSON report file creation."""
    mesh = trimesh.creation.box(extents=(10.0, 10.0, 10.0))
    config = ScaleConfig(marker_size_mm=100.0)
    processor = MetricScalingProcessor(config)
    
    _, result = processor.process(mesh, reconstructed_marker_size=50.0)
    report_path = processor.save_report(result, str(tmp_path))
    
    assert os.path.exists(report_path)