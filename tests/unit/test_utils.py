"""Tests for utility modules (paths, hashing, logging)."""

from __future__ import annotations

from pathlib import Path
import pytest
from loom.utils.hashing import compute_file_sha256
from loom.utils.paths import ensure_directory, resolve_path


def test_ensure_directory(tmp_path: Path) -> None:
    """Verify ensure_directory creates nested directories."""
    nested = tmp_path / "sub1" / "sub2"
    assert not nested.exists()
    out = ensure_directory(nested)
    assert out.is_dir()
    assert nested.exists()


def test_resolve_path() -> None:
    """Verify resolve_path returns absolute Path."""
    p = resolve_path("configs/default.yaml")
    assert p.is_absolute()


def test_compute_file_sha256(tmp_path: Path) -> None:
    """Verify SHA-256 computation matches known digest."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("VIDEO2PRINT", encoding="utf-8")
    digest = compute_file_sha256(test_file)
    assert isinstance(digest, str)
    assert len(digest) == 64

    # Non-existent file raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        compute_file_sha256(tmp_path / "does_not_exist.txt")


def test_build_subprocess_env_prepends_cuda_lib_dir(tmp_path: Path) -> None:
    """Verify _build_subprocess_env prepends CUDA lib dir when present without duplicating."""
    import os
    from loom.utils.subprocess import _build_subprocess_env

    fake_cuda = tmp_path / "cuda" / "lib64"
    fake_cuda.mkdir(parents=True)

    # Empty LD_LIBRARY_PATH
    env1 = _build_subprocess_env(env={"PATH": "/usr/bin"}, cuda_lib_dir=fake_cuda)
    assert env1["LD_LIBRARY_PATH"] == str(fake_cuda)

    # Existing LD_LIBRARY_PATH preserved after CUDA dir
    env2 = _build_subprocess_env(
        env={"LD_LIBRARY_PATH": "/usr/local/lib"},
        cuda_lib_dir=fake_cuda,
    )
    assert env2["LD_LIBRARY_PATH"] == f"{fake_cuda}{os.pathsep}/usr/local/lib"

    # Already present later in LD_LIBRARY_PATH is moved to front without duplication
    env3 = _build_subprocess_env(
        env={"LD_LIBRARY_PATH": f"/usr/local/lib{os.pathsep}{fake_cuda}"},
        cuda_lib_dir=fake_cuda,
    )
    assert env3["LD_LIBRARY_PATH"] == f"{fake_cuda}{os.pathsep}/usr/local/lib"

    # Non-existent CUDA dir leaves LD_LIBRARY_PATH untouched
    env4 = _build_subprocess_env(
        env={"LD_LIBRARY_PATH": "/usr/local/lib"},
        cuda_lib_dir=tmp_path / "missing_cuda",
    )
    assert env4["LD_LIBRARY_PATH"] == "/usr/local/lib"

