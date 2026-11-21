"""Printability exception hierarchy."""

from __future__ import annotations


class PrintabilityError(Exception):
    """Base exception for all printability validation failures."""


class PrintabilityValidationError(PrintabilityError, ValueError):
    """Raised when a 3D mesh fails the manufacturing readiness printability gate."""

    def __init__(self, message: str, validation_result: Any = None) -> None:
        super().__init__(message)
        self.validation_result = validation_result

