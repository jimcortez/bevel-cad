"""
cadquery-web-viewer integration (remote mode).

Every render is pushed as **one** viewer object -- an assembly with one named part per body
(see ``bevel_cad.render.assembly``). The bytes sent are ``<stem>.viewer.glb`` from the bundle,
so ``bevel render --viewer`` and ``bevel upload`` show exactly the same thing. The viewer is a
separately running process; everything here talks to it over HTTP.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from bevel_cad.render.bundle import RenderBundle

logger = logging.getLogger(__name__)


class ViewerUnavailable(RuntimeError):
    """``cadquery_web_viewer`` is not installed."""


class ViewerUnreachable(RuntimeError):
    """No viewer answered at the configured host/port."""


@dataclass(frozen=True)
class RunMeta:
    """Notes/settings attached to the uploaded viewer object so it can be traced back to its bundle."""

    run_name: str = ""
    stem: str = ""
    bundle_dir: str = ""
    part: str = ""
    parts: Tuple[str, ...] = ()

    def notes(self) -> str:
        lines = [f"bevel {self.run_name}".rstrip()]
        if self.bundle_dir:
            lines.append(f"bundle: {self.bundle_dir}")
        if self.part:
            lines.append(f"part: {self.part}")
        if self.parts:
            lines.append(f"parts: {', '.join(self.parts)}")
        return "\n".join(lines)

    def settings(self) -> Dict[str, Any]:
        # Viewer settings values must be str | number | null.
        return {
            "bevel.run_name": self.run_name,
            "bevel.stem": self.stem,
            "bevel.bundle_dir": self.bundle_dir,
            "bevel.part": self.part,
            "bevel.parts": ", ".join(self.parts),
            "bevel.part_count": len(self.parts),
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
        raise ViewerUnavailable("cadquery-web-viewer is not installed; pip install 'cadquery-web-viewer>=2.3'") from exc
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


def push_assembly(
    cfg: Any,
    name: str,
    glb_bytes: bytes,
    manifest: Dict[str, Any],
    *,
    auto_clear: bool = True,
    meta: Optional[RunMeta] = None,
) -> str:
    """Upload an assembly GLB (``<stem>.viewer.glb``) with its manifest as one viewer object."""
    if not manifest.get("parts"):
        raise ValueError(f"Assembly manifest for {name!r} has no parts")
    _show(
        glb_bytes,
        names=name,
        server_type="remote",
        remote_options=remote_options(cfg),
        block_until_disconnect=False,
        auto_clear=auto_clear,
        assembly=manifest,
        **tessellation_kwargs(cfg),
    )
    part_names = [str(p["name"]) for p in manifest["parts"]]
    logger.info(
        "Posted %s (%d parts: %s) to cadquery-web-viewer at %s", name, len(part_names), ", ".join(part_names), viewer_url(cfg)
    )
    _patch_meta(name, cfg, meta)
    return name


def push_artifacts(ctx: Any, run: Any) -> str:
    """Push a rendered part as one assembly object named after the run."""
    glb, _content_hash, kwargs = ctx.ensure_viewer_glb()
    manifest = dict(kwargs["assembly"])
    meta = RunMeta(
        run_name=run.run_name, stem=run.stem, bundle_dir=str(run.bundle_dir), part=str(run.part_source or ""),
        parts=tuple(str(p["name"]) for p in manifest["parts"]),
    )
    return push_assembly(run.cfg, run.run_name, glb, manifest, meta=meta)


def upload_bundle(bundle: RenderBundle, cfg: Any, *, name: Optional[str] = None) -> List[str]:
    """Re-upload an existing bundle's viewer GLB and manifest as one assembly object."""
    ensure_reachable(cfg)
    manifest = json.loads(bundle.assembly_json.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not manifest.get("parts"):
        raise ValueError(f"Assembly manifest {bundle.assembly_json} is empty or malformed")
    obj_name = name or str(cfg.rendering.name or manifest.get("name") or bundle.stem)
    manifest["name"] = obj_name
    meta = RunMeta(
        run_name=obj_name, stem=bundle.stem, bundle_dir=str(bundle.bundle_dir), part=str(cfg.get("part") or ""),
        parts=tuple(str(p["name"]) for p in manifest["parts"]),
    )
    logger.info("Uploading %s to cadquery-web-viewer as %r", bundle.viewer_glb_path, obj_name)
    return [push_assembly(cfg, obj_name, bundle.viewer_glb_path.read_bytes(), manifest, meta=meta)]
