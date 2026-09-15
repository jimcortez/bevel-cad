"""Mesh helpers: B-rep fusing, tessellation/conversion, inspection, watertightness checks."""

from .convert import assembly_to_glb_bytes, glb_bytes_to_trimesh, solid_to_glb_bytes, solid_to_trimesh
from .fuse import assert_single_solid, fuse_part_solids, fuse_solids_map_reduce, release_shapes
from .inspect import MeshLoadError, MeshReport, inspect_mesh_file, load_mesh, summarize_mesh
from .validate import require_watertight, validate_solids_watertight

__all__ = [
    "MeshLoadError",
    "MeshReport",
    "assembly_to_glb_bytes",
    "assert_single_solid",
    "fuse_part_solids",
    "fuse_solids_map_reduce",
    "glb_bytes_to_trimesh",
    "inspect_mesh_file",
    "load_mesh",
    "release_shapes",
    "require_watertight",
    "solid_to_glb_bytes",
    "solid_to_trimesh",
    "summarize_mesh",
    "validate_solids_watertight",
]
