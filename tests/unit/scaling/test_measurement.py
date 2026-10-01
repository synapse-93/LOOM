"""Unit tests for measurement engine and scale estimation."""

from __future__ import annotations

import math
import numpy as np
import pytest

from loom.scaling.exceptions import ReferenceMeasurementError, ScaleEstimationError
from loom.scaling.measurement import MeasurementEngine, ScaleEstimator


def test_scale_calculation_ratios() -> None:
    """Verify core scale factor relationship: scale = known_physical / reconstructed."""
    # known = 50, reconstructed = 25 -> scale = 2.0
    est1 = ScaleEstimator.estimate(known_physical_size_mm=50.0, measurement=25.0)
    assert est1.scale_factor == pytest.approx(2.0)

    # 50 / 50 = 1.0
    est2 = ScaleEstimator.estimate(known_physical_size_mm=50.0, measurement=50.0)
    assert est2.scale_factor == pytest.approx(1.0)

    # 50 / 100 = 0.5
    est3 = ScaleEstimator.estimate(known_physical_size_mm=50.0, measurement=100.0)
    assert est3.scale_factor == pytest.approx(0.5)


def test_floating_point_tolerances() -> None:
    """Verify precision with arbitrary floating point values."""
    known = 42.1234
    recon = 17.8912
    expected = known / recon
    est = ScaleEstimator.estimate(known, recon)
    assert est.scale_factor == pytest.approx(expected, rel=1e-6)


def test_multiple_measurements_aggregation() -> None:
    """Verify multiple measurements produce consistent mean, median, spread, and stable scale."""
    observations = [25.0, 25.1, 24.9, 25.0]
    meas = MeasurementEngine.from_observations(observations)

    assert meas.measurement_count == 4
    assert meas.mean == pytest.approx(25.0)
    assert meas.median == pytest.approx(25.0)
    assert meas.min_val == pytest.approx(24.9)
    assert meas.max_val == pytest.approx(25.1)
    assert meas.spread == pytest.approx(0.2)
    assert meas.std_dev == pytest.approx(np.std(observations))

    est = ScaleEstimator.estimate(known_physical_size_mm=50.0, measurement=meas)
    assert est.scale_factor == pytest.approx(2.0)
    assert est.confidence > 0.95


def test_3d_corners_measurement() -> None:
    """Verify calculating 4 perimeter edges from ordered 3D square corners."""
    # Square in XY plane at Z=10 with side length 25.0
    c0 = (0.0, 0.0, 10.0)
    c1 = (25.0, 0.0, 10.0)
    c2 = (25.0, 25.0, 10.0)
    c3 = (0.0, 25.0, 10.0)

    meas = MeasurementEngine.from_3d_corners([c0, c1, c2, c3])
    assert meas.measurement_count == 4
    for obs in meas.observations:
        assert obs == pytest.approx(25.0)

    est = ScaleEstimator.estimate(50.0, meas)
    assert est.scale_factor == pytest.approx(2.0)


def test_measurement_rejection_invalid_inputs() -> None:
    """Verify rejection of zero, negative, NaN, Inf, and empty measurements."""
    # Empty
    with pytest.raises(ReferenceMeasurementError):
        MeasurementEngine.from_observations([])

    # Zero
    with pytest.raises(ReferenceMeasurementError):
        MeasurementEngine.from_observations([25.0, 0.0, 25.0])

    # Negative
    with pytest.raises(ReferenceMeasurementError):
        MeasurementEngine.from_observations([25.0, -5.0])

    # NaN
    with pytest.raises(ReferenceMeasurementError):
        MeasurementEngine.from_observations([25.0, float("nan")])

    # Inf
    with pytest.raises(ReferenceMeasurementError):
        MeasurementEngine.from_observations([25.0, float("inf")])

    # 3D corners with incorrect count
    with pytest.raises(ReferenceMeasurementError):
        MeasurementEngine.from_3d_corners([(0, 0, 0), (1, 0, 0)])

    # 3D corners with NaN
    with pytest.raises(ReferenceMeasurementError):
        MeasurementEngine.from_3d_corners([(0, 0, 0), (1, 0, 0), (1, 1, float("nan")), (0, 1, 0)])


def test_scale_estimator_rejection_invalid_values() -> None:
    """Verify ScaleEstimator rejects zero, negative, or non-finite inputs."""
    # Known physical <= 0
    with pytest.raises(ScaleEstimationError):
        ScaleEstimator.estimate(known_physical_size_mm=0.0, measurement=25.0)

    with pytest.raises(ScaleEstimationError):
        ScaleEstimator.estimate(known_physical_size_mm=-10.0, measurement=25.0)

    with pytest.raises(ScaleEstimationError):
        ScaleEstimator.estimate(known_physical_size_mm=float("nan"), measurement=25.0)

    # Reconstructed <= 0
    with pytest.raises(ScaleEstimationError):
        ScaleEstimator.estimate(known_physical_size_mm=50.0, measurement=0.0)

    with pytest.raises(ScaleEstimationError):
        ScaleEstimator.estimate(known_physical_size_mm=50.0, measurement=-25.0)

    with pytest.raises(ScaleEstimationError):
        ScaleEstimator.estimate(known_physical_size_mm=50.0, measurement=float("inf"))
