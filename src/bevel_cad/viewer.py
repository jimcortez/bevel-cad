"""
cadquery-web-viewer integration (remote mode).

The viewer is an optional dependency (``pip install bevel-cad[viewer]``) and a
separately running process; everything here talks to it over HTTP.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from bevel_cad.render.bundle import RenderBundle

logger = logging.getLogger(__name__)


class ViewerUnavailable(RuntimeError):
    """``cadquery_web_viewer`` is not installed."""


class ViewerUnreachable(RuntimeError):
    """No viewer answered at the configured host/port."""


@dataclass(frozen=True)
class RunMeta:
    """Per-object notes/settings attached to uploaded viewer objects."""

    run_name: str = ""
    stem: str = ""
    bundle_dir: str = ""
    part: str = ""

    def notes(self) -> str:
        lines = [f"bevel {self.run_name}".rstrip()]
        if self.bundle_dir:
            lines.append(f"bundle: {self.bundle_dir}")
        if self.part:
            lines.append(f"part: {self.part}")
        return "\n".join(lines)

    def settings(self) -> Dict[str, Any]:
        return {
            "bevel.run_name": self.run_name,
            "bevel.stem": self.stem,
            "bevel.bundle_dir": self.bundle_dir,
            "bevel.part": self.part,
        }


def remote_options(cfg: Any) -> Dict[str, Any]:
    v = cfg.viewer
    return {
        "host": str(v.host),
        "port": int(v.port),
        "upload_timeout": float(v.upload_timeout),
        "post_timeout": float(v.post_timeout),
    }


def tessellation_kwargs(cfg: Any) -> Dict[str, float]:
    return {"tolerance": float(cfg.viewer.tolerance), "angular_tolerance": float(cfg.viewer.angular_tolerance)}


def viewer_url(cfg: Any) -> str:
    ro = remote_options(cfg)
    return f"http://{ro['host']}:{ro['port']}/"


def ensure_reachable(cfg: Any, *, timeout: float = 5.0) -> None:
    """Probe ``GET /api/scene``; raise :class:`ViewerUnreachable` with a start hint on failure."""
    import httpx

    ro = remote_options(cfg)
    probe_timeout = min(float(ro["post_timeout"]), float(timeout))
    url = f"http://{ro['host']}:{ro['port']}/api/scene"
    try:
        with httpx.Client(timeout=probe_timeout) as client:
            client.get(url)
    except httpx.HTTPError as exc:
        raise ViewerUnreachable(
            f"cadquery-web-viewer not reachable at http://{ro['host']}:{ro['port']}/ ({exc}). "
            f"Start it in another terminal: cadquery-web-viewer --host {ro['host']} --port {ro['port']}"
        ) from exc


def _show(*objs: Any, **kwargs: Any) -> None:
    """Thin wrapper around ``cadquery_web_viewer.show`` (patched in tests)."""
    try:
        from cadquery_web_viewer import show
    except ImportError as exc:  # pragma: no cover
        raise ViewerUnavailable("cadquery-web-viewer is not installed; pip install 'bevel-cad[viewer]'") from exc
    show(*objs, **kwargs)


def _patch_meta(name: str, cfg: Any, meta: Optional[RunMeta]) -> None:
    """Best-effort: attach notes/settings to the object; older viewers may lack PATCH."""
    if meta is None:
        return
    try:
        from cadquery_web_viewer.http_client import remote_patch_object

        remote_patch_object(name, remote_options(cfg), notes=meta.notes(), settings=meta.settings())
    except Exception as exc:  # noqa: BLE001 - never let metadata break a render
        logger.warning("Could not attach bevel metadata to viewer object %r: %s", name, exc)


def push_glb(cfg: Any, name: str, glb_bytes: bytes, *, auto_clear: bool = True, meta: Optional[RunMeta] = None) -> List[str]:
    """Upload pre-tessellated GLB bytes as one viewer object."""
    _show(
        glb_bytes,
        names=name,
        server_type="remote",
        remote_options=remote_options(cfg),
        block_until_disconnect=False,
        auto_clear=auto_clear,
        **tessellation_kwargs(cfg),
    )
    logger.info("Posted %s to cadquery-web-viewer at %s", name, viewer_url(cfg))
    _patch_meta(name, cfg, meta)
    return [name]


def push_colored_parts(cfg: Any, names: Sequence[str], shapes: Sequence[Any], *, meta: Optional[RunMeta] = None) -> List[str]:
    """Upload each (already coloured) shape as its own object; the first call clears the scene."""
    tess = tessellation_kwargs(cfg)
    ro = remote_options(cfg)
    pushed: List[str] = []
    for idx, (part_name, shape) in enumerate(zip(names, shapes)):
        _show(
            shape,
            names=part_name,
            server_type="remote",
            remote_options=ro,
            block_until_disconnect=False,
            color_faces=getattr(shape, "color", None),
            auto_clear=idx == 0,
            **tess,
        )
        _patch_meta(part_name, cfg, meta)
        pushed.append(part_name)
    logger.info("Posted %s to cadquery-web-viewer at %s", ", ".join(pushed), viewer_url(cfg))
    return pushed


def push_artifacts(ctx: Any, run: Any, *, name: str) -> List[str]:
    """
    Push a rendered part: assemblies with >= 2 bodies go up as separately coloured
    objects; everything else as the bundle GLB (preferring the file already on disk).
    """
    from bevel_cad.render.colors import colored_assembly_shapes, iter_assembly_leaf_solids
    from bevel_cad.render.planner import first_preview_settings

    cfg = run.cfg
    meta = RunMeta(run_name=run.run_name, stem=run.stem, bundle_dir=str(run.bundle_dir), part=str(run.part_source or ""))
    if ctx.is_assembly and ctx.assy is not None:
        leaves = iter_assembly_leaf_solids(ctx.assy)
        if len(leaves) >= 2:
            preview = first_preview_settings(cfg)
            base_rgb = preview.color_rgb if preview else (0.7, 0.7, 0.7)
            part_names, colored = colored_assembly_shapes(ctx.assy, base_rgb)
            return push_colored_parts(cfg, part_names, colored, meta=meta)
    glb_path = ctx.bundle_glb_path()
    glb = glb_path.read_bytes() if glb_path is not None and glb_path.is_file() else ctx.ensure_glb_bytes()
    return push_glb(cfg, name, glb, meta=meta)


def upload_bundle(bundle: RenderBundle, cfg: Any, *, name: Optional[str] = None) -> List[str]:
    """Re-upload an existing bundle's GLB."""
    ensure_reachable(cfg)
    obj_name = name or str(cfg.rendering.name or bundle.stem)
    meta = RunMeta(run_name=obj_name, stem=bundle.stem, bundle_dir=str(bundle.bundle_dir), part=str(cfg.get("part") or ""))
    logger.info("Uploading %s to cadquery-web-viewer as %r", bundle.glb_path, obj_name)
    return push_glb(cfg, obj_name, bundle.glb_path.read_bytes(), meta=meta)
