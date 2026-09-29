"""Resolve existing render bundle folders for re-upload to the web viewer."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from bevel_cad.render.naming import assembly_manifest_name

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RenderBundle:
    """Paths for a flat render bundle directory."""

    bundle_dir: Path
    stem: str
    viewer_glb_path: Path
    """``<stem>.viewer.glb`` -- the assembly GLB that ``bevel upload`` sends."""
    assembly_json: Path
    """``<stem>.assembly.json`` -- part names, colours and tags of the viewer GLB."""
    config_yaml: Path
    glb_path: Path
    """``<stem>.glb`` (plain mesh export); may not exist."""


def resolve_render_bundle(path: Path) -> RenderBundle:
    """
    Resolve a render bundle directory or its config YAML to bundle artifact paths.

    Args:
        path: Bundle directory or ``{stem}.yaml`` inside the bundle.

    Returns:
        RenderBundle with absolute paths.

    Raises:
        ValueError: If ``path`` is not a directory or YAML file.
        FileNotFoundError: If the viewer GLB or assembly manifest is missing (bundles rendered
            before assembly uploads existed, or with ``rendering.exports.viewer`` disabled).
    """
    resolved = path.resolve()
    if resolved.is_file() and resolved.suffix in {".yaml", ".yml"}:
        bundle_dir = resolved.parent
        stem = bundle_dir.name
    elif resolved.is_dir():
        bundle_dir = resolved
        stem = resolved.name
    else:
        raise ValueError(
            f"Render bundle path must be a directory or YAML file, got: {path}"
        )

    viewer_glb_path = bundle_dir / f"{stem}.viewer.glb"
    assembly_json = bundle_dir / assembly_manifest_name(stem)
    config_yaml = bundle_dir / f"{stem}.yaml"
    glb_path = bundle_dir / f"{stem}.glb"

    for required, label in ((viewer_glb_path, "Viewer GLB"), (assembly_json, "Assembly manifest")):
        if not required.is_file():
            raise FileNotFoundError(
                f"{label} not found: {required}. This bundle predates assembly uploads or was rendered "
                "with rendering.exports.viewer disabled; re-render it with the viewer export enabled."
            )

    if not config_yaml.is_file():
        logger.info(
            "Render bundle config YAML not found at %s; upload will use project config only",
            config_yaml,
        )

    return RenderBundle(
        bundle_dir=bundle_dir,
        stem=stem,
        viewer_glb_path=viewer_glb_path,
        assembly_json=assembly_json,
        config_yaml=config_yaml,
        glb_path=glb_path,
    )
