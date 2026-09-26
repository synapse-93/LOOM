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
