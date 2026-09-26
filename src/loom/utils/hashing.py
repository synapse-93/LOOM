"""File and artifact hashing utilities for provenance and caching."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Union


def compute_file_sha256(path: Union[str, Path], chunk_size: int = 65536) -> str:
    """Compute SHA-256 hash of a file for deterministic provenance tracking.

    Args:
        path: Path to target file.
        chunk_size: Byte chunk size for streaming read.

    Returns:
        Hexadecimal SHA-256 digest string.
    """
    p = Path(path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"File not found for hashing: {p}")

    hasher = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)

    return hasher.hexdigest()
