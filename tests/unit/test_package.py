"""Tests for top-level package imports and metadata."""

from __future__ import annotations


def test_package_import() -> None:
    """Verify loom package imports cleanly."""
    import loom
    assert loom.__version__ == "0.1.0"


def test_submodules_importable() -> None:
    """Verify all submodules import without circular dependency errors."""
    import loom.config
    import loom.pipeline
    import loom.video
    import loom.capture
    import loom.reconstruction
    import loom.pointcloud
    import loom.mesh
    import loom.scaling
    import loom.validation
    import loom.printability
    import loom.export
    import loom.geometry
    import loom.utils
    assert True
