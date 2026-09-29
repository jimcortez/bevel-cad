"""
3MF export with welded, closed meshes (written by trimesh's 3MF exporter, which needs lxml).

CadQuery's 3MF exporter tessellates every B-rep face separately and never shares vertices between
faces, so a slicer sees every face boundary as an open edge (a solid sewn from triangles comes out
with *every* edge open). Here each body is tessellated once, identical vertex positions are merged
with trimesh, and the scene is written by ``trimesh.exchange.threemf.export_3MF``: one named object
per body whose triangles index a shared vertex list. A body that came from a closed solid must come
out watertight, otherwise the export fails.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Sequence, Tuple

import numpy as np
import trimesh
from trimesh.exchange.threemf import export_3MF

NamedMesh = Tuple[str, trimesh.Trimesh]


class ThreeMfError(RuntimeError):
    """A body cannot be written as a valid 3MF mesh object."""


def open_edge_count(mesh: trimesh.Trimesh) -> int:
    """Edges used by exactly one triangle (0 for a closed mesh)."""
    return len(trimesh.grouping.group_rows(mesh.edges_sorted, require_count=1))


def weld_body(name: str, mesh: trimesh.Trimesh, *, require_closed: bool) -> trimesh.Trimesh:
    """A copy of ``mesh`` with identical vertex positions merged (``Trimesh.merge_vertices``).

    Raises when the mesh is empty, a triangle repeats a vertex after welding (invalid in 3MF), or
    ``require_closed`` is set and the welded mesh is not watertight.
    """
    welded = trimesh.Trimesh(
        vertices=np.asarray(mesh.vertices, dtype=np.float64), faces=np.asarray(mesh.faces, dtype=np.int64), process=False
    )
    if len(welded.faces) == 0:
        raise ThreeMfError(f"3MF body {name!r} has no triangles.")
    welded.merge_vertices()
    faces = welded.faces
    repeated = (faces[:, 0] == faces[:, 1]) | (faces[:, 1] == faces[:, 2]) | (faces[:, 2] == faces[:, 0])
    if repeated.any():
        raise ThreeMfError(
            f"3MF body {name!r}: {int(repeated.sum())} of {len(faces)} triangles repeat a vertex after welding "
            "(degenerate tessellation); 3MF requires three distinct vertices per triangle."
        )
    if require_closed and not welded.is_watertight:
        raise ThreeMfError(
            f"3MF body {name!r} comes from a closed solid but its welded tessellation has "
            f"{open_edge_count(welded)} open edges; the faces' tessellations do not meet."
        )
    return welded


def write_3mf(path: Path, bodies: Sequence[NamedMesh]) -> None:
    """Write ``bodies`` as one named 3MF object and build item each (millimetres) via trimesh."""
    if not bodies:
        raise ThreeMfError("Nothing to write: no bodies for the 3MF.")
    names: List[str] = [name for name, _ in bodies]
    if len(set(names)) != len(names):
        raise ThreeMfError(f"3MF body names must be unique: {names}")
    scene = trimesh.Scene()
    for name, mesh in bodies:
        scene.add_geometry(mesh, geom_name=name, node_name=name)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(export_3MF(scene))
