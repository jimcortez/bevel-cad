"""
Build ``<stem>.viewer.glb``: the assembly GLB cadquery-web-viewer displays.

The viewer's own tessellator produces one glTF node per part with faces, edges and vertices,
so the browser can toggle and recolour parts individually. The same bytes are sent by
``bevel render --viewer`` and ``bevel upload``.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from bevel_cad.render.assembly import AssemblyManifest, PartEntry
from bevel_cad.render.errors import ExportError

ViewerGlb = Tuple[bytes, str, Dict[str, Any]]
"""``(glb_bytes, content_hash, kwargs)``; ``kwargs["assembly"]`` is the manifest embedded in the GLB."""

_INSTALL_HINT = (
    "cadquery-web-viewer with assembly support is required for the viewer GLB export "
    "(rendering.exports.viewer); install/upgrade it: pip install 'cadquery-web-viewer>=2.3'"
)


def _viewer_api() -> Any:
    try:
        import cadquery_web_viewer.assembly as assembly_mod
        from cadquery_web_viewer.engine import prepare_assembly_upload
        from cadquery_web_viewer.gltf import GLTFMgr
    except ImportError as exc:
        raise ExportError(f"{_INSTALL_HINT} ({exc})") from exc
    return assembly_mod, prepare_assembly_upload, GLTFMgr


def _hex_to_rgba(color: str | None) -> Tuple[float, float, float, float] | None:
    if color is None:
        return None
    c = color.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (r, g, b, 1.0)


def build_viewer_glb(manifest: AssemblyManifest, cfg: Any) -> ViewerGlb:
    """Tessellate every part of ``manifest`` into one assembly GLB using the viewer's tessellator."""
    assembly_mod, prepare_assembly_upload, GLTFMgr = _viewer_api()
    tess = {"tolerance": float(cfg.viewer.tolerance), "angular_tolerance": float(cfg.viewer.angular_tolerance)}
    if any(p.is_mesh for p in manifest.parts):
        return _build_mesh_glb(manifest, cfg, assembly_mod, GLTFMgr)
    spec = assembly_mod.AssemblySpec(
        name=manifest.name,
        tags=tuple(manifest.tags),
        parts=tuple(
            assembly_mod.AssemblyPart(name=p.name, obj=p.shape, color=_hex_to_rgba(p.color), tags=tuple(p.tags))
            for p in manifest.parts
        ),
    )
    name, glb, content_hash, kwargs = prepare_assembly_upload(spec, manifest.name, **tess)
    if name != manifest.name or not glb.startswith(b"glTF"):
        raise ExportError(f"cadquery-web-viewer returned an unexpected payload for {manifest.name!r}")
    return glb, content_hash, kwargs


def _build_mesh_glb(manifest: AssemblyManifest, cfg: Any, assembly_mod: Any, GLTFMgr: Any) -> ViewerGlb:
    """Mesh parts have no B-rep to tessellate: feed the triangles straight into the viewer's GLTF builder."""
    import numpy as np
    from cadquery_web_viewer.cad import _hashcode

    manifest_json = manifest.to_dict()
    mgr = GLTFMgr()
    mgr.set_assembly(manifest.name, manifest_json)
    style_faces = cfg.viewer.style.color_faces
    default: Tuple[float, float, float, float] = (_hex_to_rgba(str(style_faces)) if style_faces else None) or (1.0, 0.75, 0.0, 1.0)
    for part in manifest.parts:
        _add_mesh_part(mgr, part, part_color=_hex_to_rgba(part.color) or default, np=np)
    glb = b"".join(mgr.build().save_to_bytes())
    kwargs = {"assembly": manifest_json}
    return glb, _hashcode(glb, **kwargs), kwargs


def _add_mesh_part(mgr: Any, part: PartEntry, *, part_color: Tuple[float, float, float, float], np: Any) -> None:
    if not part.is_mesh:
        raise ExportError(f"Part {part.name!r} is a B-rep body; mesh and B-rep parts cannot be mixed")
    mesh = part.shape
    verts = np.asarray(mesh.vertices, dtype=float)
    normals = np.asarray(mesh.vertex_normals, dtype=float)
    faces = np.asarray(mesh.faces, dtype=int)
    if len(faces) == 0:
        raise ExportError(f"Mesh part {part.name!r} has no faces")
    # Z-up (mm, CAD) -> Y-up (glTF), the same rotation the viewer applies to B-rep shapes.
    to_yup = lambda a: [(float(x), float(z), float(-y)) for x, y, z in a]  # noqa: E731
    mgr.begin_part(part.name)
    mgr.add_face(
        to_yup(verts),
        to_yup(normals),
        [(int(a), int(b), int(c)) for a, b, c in faces],
        [(0.0, 0.0)] * len(verts),
        part_color,
    )
