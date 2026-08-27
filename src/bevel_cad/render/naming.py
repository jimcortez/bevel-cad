"""Run names, bundle stems, and export filename templates."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Dict

DEFAULT_FILENAME_TEMPLATES: Dict[str, str] = {
    "stl": "{name}.stl",
    "step": "{name}.step",
    "3mf": "{name}.3mf",
    "glb": "{name}.glb",
    "gltf": "{name}.gltf",
    "obj": "{name}.obj",
    "preview": "{name}.png",
    "config": "{name}.yaml",
    "stats": "{name}.csv",
}

VALID_EXPORT_FORMATS = frozenset(DEFAULT_FILENAME_TEMPLATES.keys())


def slugify(s: str) -> str:
    """Lowercase, replace non-alphanumeric runs with '-', strip leading/trailing '-'."""
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def render_bundle_stem(run_name: str, *, now: datetime | None = None) -> str:
    """``<slug(run_name)>_<YYYYMMDD-HHMMSS>`` -- the bundle directory name and file stem."""
    ts = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return f"{slugify(run_name or 'part')}_{ts}"


def resolve_filename_template(template: str, *, bundle_stem: str, run_name: str) -> str:
    """Substitute ``{name}`` (bundle stem) and ``{run_name}`` (raw run name) in an export filename."""
    return template.replace("{name}", bundle_stem).replace("{run_name}", run_name)


def body_slug(name: str) -> str:
    """Slug used for per-body STL suffixes; keeps case and underscores."""
    return re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-") or "body"
