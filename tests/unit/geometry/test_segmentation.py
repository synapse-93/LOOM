"""Unit tests for ForegroundSegmenter."""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest
import trimesh

from loom.geometry.segmentation import ForegroundSegmenter, SegmentationResult


def test_segment_empty_point_cloud() -> None:
    """Verify segmenting an empty cloud returns 0 points without error."""
    segmenter = ForegroundSegmenter()
    empty_pc = trimesh.PointCloud(vertices=np.empty((0, 3)))
    out_pc, res = segmenter.segment(empty_pc)

    assert len(out_pc.vertices) == 0
    assert res.points_before == 0
    assert res.points_after == 0


def test_segment_sub_table_noise_discard() -> None:
    """Verify points with Z < -0.01 are discarded as sub-table noise."""
    segmenter = ForegroundSegmenter(z_min_cutoff=-0.01)

    pts = np.array([
        [0.0, 0.0, -0.05],  # sub-table noise
        [0.1, 0.1, -0.02],  # sub-table noise
        [0.0, 0.0, 0.00],   # table surface (kept)
        [0.1, 0.0, 0.05],   # object point (kept)
    ])
    pc = trimesh.PointCloud(vertices=pts)
    out_pc, res = segmenter.segment(pc)

    assert res.sub_table_points_removed == 2
    assert len(out_pc.vertices) == 2
    assert np.all(out_pc.vertices[:, 2] >= -0.01)


def test_segment_background_clutter_cylindrical_crop(tmp_path: Path) -> None:
    """Verify radial cylindrical crop removes distant background clutter."""
    segmenter = ForegroundSegmenter(
        z_min_cutoff=-0.01,
        z_elevated_cutoff=0.02,
        radial_multiplier=1.25,
        radius_percentile=98.0,
    )

    rng = np.random.default_rng(42)

    # 1. Foreground object: 200 points clustered within radius 0.5 around (1.0, 2.0), Z in [0.03, 0.5]
    n_obj = 200
    angles = rng.uniform(0, 2 * np.pi, n_obj)
    radii = rng.uniform(0, 0.5, n_obj)
    obj_x = 1.0 + radii * np.cos(angles)
    obj_y = 2.0 + radii * np.sin(angles)
    obj_z = rng.uniform(0.03, 0.5, n_obj)
    obj_pts = np.column_stack([obj_x, obj_y, obj_z])

    # 2. Support plane points underneath object: 50 points, Z = 0
    plane_pts = np.column_stack([
        1.0 + rng.uniform(-0.4, 0.4, 50),
        2.0 + rng.uniform(-0.4, 0.4, 50),
        np.zeros(50),
    ])

    # 3. Background clutter: 30 points far away (radius ~ 3.0), Z in [0.03, 1.0]
    bg_x = rng.uniform(5.0, 8.0, 30)
    bg_y = rng.uniform(5.0, 8.0, 30)
    bg_z = rng.uniform(0.03, 1.0, 30)
    bg_pts = np.column_stack([bg_x, bg_y, bg_z])

    all_pts = np.vstack([obj_pts, plane_pts, bg_pts])
    pc = trimesh.PointCloud(vertices=all_pts)

    out_file = tmp_path / "fused_isolated.ply"
    out_pc, res = segmenter.segment(pc, output_path=out_file)

    assert out_file.is_file()
    assert res.background_points_removed == 30
    assert np.isclose(res.object_center_xy[0], 1.0, atol=0.1)
    assert np.isclose(res.object_center_xy[1], 2.0, atol=0.1)
    assert len(out_pc.vertices) == 250

