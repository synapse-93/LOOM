"""Logging configuration utilities for LOOM."""

from __future__ import annotations

import logging
import sys
from typing import Optional


def setup_logging(level: str = "INFO", log_format: Optional[str] = None) -> None:
    """Configure root logger for LOOM pipeline execution.

    Args:
        level: Logging level (e.g. 'DEBUG', 'INFO', 'WARNING', 'ERROR').
        log_format: Optional custom format string.
    """
    if log_format is None:
        log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format=log_format,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    """Return a module logger with standard configuration."""
    return logging.getLogger(name)
