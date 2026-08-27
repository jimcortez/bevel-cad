"""Conversions between CadQuery B-rep shapes, trimesh meshes, and GLB bytes."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import cadquery as cq
import trimesh


def _tmp(suffix: str) -> str:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
        return tf.name


def _unlink(*paths: str) -> None:
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass


def assembly_to_glb_bytes(assy: cq.Assembly, *, tolerance: float, angular_tolerance: float) -> bytes:
    """Tessellate a ``cq.Assembly`` (keeping named nodes) into GLB bytes."""
    tmp = _tmp(".glb")
    try:
        assy.export(tmp, exportType="GLB", tolerance=float(tolerance), angularTolerance=float(angular_tolerance))
        return Path(tmp).read_bytes()
    finally:
        _unlink(tmp)


def solid_to_trimesh(solid: Any, *, tolerance: float = 0.05, angular_tolerance: float = 0.3) -> trimesh.Trimesh:
    """Tessellate a CadQuery shape via a temporary binary STL into a single ``Trimesh``."""
    tmp = _tmp(".stl")
    try:
        cq.exporters.export(
            solid, tmp, tolerance=float(tolerance), angularTolerance=float(angular_tolerance), opt={"ascii": False}
        )
        loaded = trimesh.load(tmp)
        return loaded.to_geometry() if isinstance(loaded, trimesh.Scene) else loaded
    finally:
        _unlink(tmp)


def solid_to_glb_bytes(solid: Any, *, tolerance: float, angular_tolerance: float) -> bytes:
    """Tessellate a single CadQuery shape into GLB bytes (STL -> trimesh -> GLB)."""
    mesh = solid_to_trimesh(solid, tolerance=tolerance, angular_tolerance=angular_tolerance)
    return mesh.export(file_type="glb")


def glb_bytes_to_trimesh(glb: bytes) -> trimesh.Trimesh:
    """Load GLB bytes and concatenate any scene into one ``Trimesh``."""
    scene_or_mesh = trimesh.load(trimesh.util.wrap_as_stream(glb), file_type="glb")
    if isinstance(scene_or_mesh, trimesh.Scene):
        return scene_or_mesh.to_geometry()
    return scene_or_mesh
