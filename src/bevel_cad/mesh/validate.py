"""Geometry validation helpers for print-ready solids."""

from __future__ import annotations

from typing import Any, Iterable, List, Tuple

from .convert import solid_to_trimesh


def validate_solids_watertight(
    solids: Iterable[Tuple[str, Any]],
    *,
    tolerance: float = 0.05,
) -> List[str]:
    """
    Check each ``(name, solid)`` is a valid OCC shape that tessellates to a
    watertight mesh with positive volume.

    Returns human-readable error strings; an empty list means everything passed.
    """
    errors: List[str] = []
    for name, solid in solids:
        if hasattr(solid, "isValid") and not solid.isValid():
            errors.append(f"{name}: CadQuery/OCC shape is invalid")
            continue
        mesh = solid_to_trimesh(solid, tolerance=tolerance)
        if not mesh.is_watertight:
            errors.append(f"{name}: tessellated mesh is not watertight")
        if mesh.volume <= 0:
            errors.append(f"{name}: non-positive volume ({mesh.volume:.4f} mm³)")
    return errors


def require_watertight(solids: Iterable[Tuple[str, Any]], *, what: str = "part", tolerance: float = 0.05) -> None:
    """Raise ``RuntimeError`` listing every failure from :func:`validate_solids_watertight`."""
    errors = validate_solids_watertight(solids, tolerance=tolerance)
    if errors:
        raise RuntimeError(f"{what} geometry validation failed:\n  " + "\n  ".join(errors))
