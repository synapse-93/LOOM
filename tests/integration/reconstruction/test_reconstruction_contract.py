"""Contract and interface tests for interchangeable reconstruction engine adapters."""

from __future__ import annotations

from pathlib import Path
import pytest
from loom.reconstruction.base import ReconstructionEngine
from loom.reconstruction.colmap import ColmapAdapter
from loom.reconstruction.meshroom import MeshroomAdapter
from loom.reconstruction.models import ReconstructionJobConfig
from loom.reconstruction.runner import ReconstructionRunner


def test_reconstruction_runner_factory() -> None:
    """Verify ReconstructionRunner provides valid instances of configured engines."""
    engine_meshroom = ReconstructionRunner.get_engine("meshroom")
    assert isinstance(engine_meshroom, ReconstructionEngine)
    assert engine_meshroom.backend_name == "meshroom"

    engine_colmap = ReconstructionRunner.get_engine("colmap")
    assert isinstance(engine_colmap, ReconstructionEngine)
    assert engine_colmap.backend_name == "colmap"

    with pytest.raises(ValueError, match="Unknown reconstruction backend"):
        ReconstructionRunner.get_engine("non_existent_engine")


def test_meshroom_adapter_contract() -> None:
    """Verify MeshroomAdapter respects the ReconstructionEngine contract."""
    adapter = MeshroomAdapter()
    assert adapter.backend_name == "meshroom"
    # is_available returns boolean without raising
    is_avail = adapter.is_available()
    assert isinstance(is_avail, bool)

    # reconstruct raises NotImplementedError during scaffold iteration
    cfg = ReconstructionJobConfig(workspace_dir=Path("outputs/test"))
    with pytest.raises(NotImplementedError, match="Phase 2"):
        adapter.reconstruct([], cfg)


def test_colmap_adapter_contract() -> None:
    """Verify ColmapAdapter respects the ReconstructionEngine contract."""
    adapter = ColmapAdapter()
    assert adapter.backend_name == "colmap"
    is_avail = adapter.is_available()
    assert isinstance(is_avail, bool)

    cfg = ReconstructionJobConfig(workspace_dir=Path("outputs/test"))
    with pytest.raises(NotImplementedError):
        adapter.reconstruct([], cfg)
