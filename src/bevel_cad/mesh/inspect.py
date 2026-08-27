"""Mesh diagnostics: watertightness, components, boundary / non-manifold edges."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np
import trimesh


class MeshLoadError(ValueError):
    """Raised when a file cannot be loaded as a single triangle mesh."""


@dataclass
class MeshReport:
    path: str
    watertight: bool
    vertices: int
    faces: int
    components: Optional[int]
    volume: Optional[float]
    bounds_min: Optional[List[float]]
    bounds_max: Optional[List[float]]
    boundary_edges: Optional[int]
    nonmanifold_edges: Optional[int]
    trimesh_version: str = trimesh.__version__

    @property
    def extents(self) -> Optional[List[float]]:
        if self.bounds_min is None or self.bounds_max is None:
            return None
        return [float(b - a) for a, b in zip(self.bounds_min, self.bounds_max)]

    @property
    def ok(self) -> bool:
        """True when the mesh is watertight, a single component, and has no open edges."""
        return bool(
            self.watertight
            and (self.components in (None, 1))
            and (self.boundary_edges in (None, 0))
            and (self.nonmanifold_edges in (None, 0))
        )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["extents"] = self.extents
        d["ok"] = self.ok
        return d

    def format_text(self) -> str:
        lines = [
            f"File: {self.path}",
            f"  Watertight: {self.watertight}",
            f"  Vertices:  {self.vertices}",
            f"  Faces:     {self.faces}",
            f"  Components (all): {self.components if self.components is not None else '<error>'}",
        ]
        if self.volume is not None:
            lines.append(f"  Volume:    {self.volume:.3f}")
        if self.extents is not None:
            lines.append("  Extents:   " + " x ".join(f"{e:.3f}" for e in self.extents))
        if self.boundary_edges is not None:
            lines.append(f"  Boundary edges:   {self.boundary_edges}")
            if self.boundary_edges > 0:
                lines.append("    NOTE: Non-zero boundary edges indicate leaks/open surfaces.")
        else:
            lines.append("  Boundary edges:   <unavailable on this trimesh version>")
        if self.nonmanifold_edges is not None:
            lines.append(f"  Non-manifold edges: {self.nonmanifold_edges}")
            if self.nonmanifold_edges > 0:
                lines.append("    NOTE: Non-manifold edges may cause issues in slicing/meshing.")
        else:
            lines.append("  Non-manifold edges: <unavailable on this trimesh version>")
        lines.append(f"  Trimesh:   {self.trimesh_version}")
        return "\n".join(lines)


def load_mesh(path: Union[str, Path]) -> trimesh.Trimesh:
    """Load any trimesh-readable file as a single ``Trimesh`` (scenes are concatenated)."""
    path = Path(path)
    try:
        scene_or_mesh = trimesh.load(path)
    except Exception as exc:  # trimesh raises a wide variety of errors
        raise MeshLoadError(f"Failed to load mesh '{path}': {exc!r}") from exc
    if isinstance(scene_or_mesh, trimesh.Scene):
        if not scene_or_mesh.geometry:
            raise MeshLoadError(f"Mesh '{path}' contains an empty Scene.")
        mesh = scene_or_mesh.to_geometry()
    else:
        mesh = scene_or_mesh
    if not isinstance(mesh, trimesh.Trimesh):
        raise MeshLoadError(f"Loaded object from '{path}' is not a Trimesh (got {type(mesh)!r}).")
    return mesh


def _edge_incidence_counts(mesh: trimesh.Trimesh) -> Optional[np.ndarray]:
    """Faces-per-unique-edge counts; trimesh>=4 no longer exposes ``edges_face_count``."""
    try:
        fue = np.asarray(mesh.faces_unique_edges)
        if fue.size == 0:
            return np.zeros((0,), dtype=np.int64)
        return np.bincount(fue.reshape(-1), minlength=len(mesh.edges_unique))
    except Exception:
        return None


def summarize_mesh(mesh: trimesh.Trimesh, path: Union[str, Path] = "<memory>") -> MeshReport:
    """Compute a :class:`MeshReport` for an in-memory mesh."""
    try:
        components: Optional[int] = len(mesh.split(only_watertight=False))
    except Exception:
        components = None
    try:
        volume: Optional[float] = float(mesh.volume) if mesh.is_watertight else None
    except Exception:
        volume = None
    try:
        bmin, bmax = mesh.bounds
        bounds_min, bounds_max = [float(x) for x in bmin], [float(x) for x in bmax]
    except Exception:
        bounds_min = bounds_max = None

    boundary_count: Optional[int] = None
    nonmanifold_count: Optional[int] = None
    efc = _edge_incidence_counts(mesh)
    if efc is not None:
        boundary_count = int((efc == 1).sum())
        nonmanifold_count = int((efc > 2).sum())
    else:
        eb = getattr(mesh, "edges_boundary", None)
        if eb is not None:
            try:
                boundary_count = len(eb)
            except TypeError:
                pass
        en = getattr(mesh, "edges_nonmanifold", None)
        if en is not None:
            try:
                nonmanifold_count = len(en)
            except TypeError:
                pass

    return MeshReport(
        path=str(path),
        watertight=bool(mesh.is_watertight),
        vertices=int(len(mesh.vertices)),
        faces=int(len(mesh.faces)),
        components=components,
        volume=volume,
        bounds_min=bounds_min,
        bounds_max=bounds_max,
        boundary_edges=boundary_count,
        nonmanifold_edges=nonmanifold_count,
    )


def inspect_mesh_file(path: Union[str, Path]) -> MeshReport:
    """Load ``path`` and summarize it. Never modifies the file."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Mesh file not found: {path}")
    return summarize_mesh(load_mesh(path), path)
