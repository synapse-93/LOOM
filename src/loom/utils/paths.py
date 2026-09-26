"""Filesystem and path resolution utilities for LOOM."""

from __future__ import annotations

from pathlib import Path
from typing import Union


def resolve_path(path: Union[str, Path], base_dir: Union[str, Path, None] = None) -> Path:
    """Normalize and resolve a filesystem path.

    Args:
        path: Path string or Path object.
        base_dir: Optional base directory to resolve relative paths against.

    Returns:
        Resolved absolute Path.
    """
    p = Path(path)
    if not p.is_absolute() and base_dir is not None:
        p = Path(base_dir) / p
    return p.resolve()


def ensure_directory(path: Union[str, Path]) -> Path:
    """Ensure directory exists, creating parents if necessary.

    Args:
        path: Directory path.

    Returns:
        Resolved Path to the directory.
    """
    p = Path(path).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p
