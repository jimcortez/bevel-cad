"""Exceptions shared by the render modules."""

from __future__ import annotations


class ExportError(RuntimeError):
    """An export job could not be completed."""
