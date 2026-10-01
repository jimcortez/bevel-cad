"""
The viewer assembly: what a render's bodies are called, how they are coloured and tagged.

Every render is uploaded to cadquery-web-viewer as **one** assembly object with named parts:
a ``cq.Assembly`` contributes one part per body (in ``traverse()`` order, world coordinates
applied), anything else is a single part named after the run. The :class:`AssemblyManifest`
is serialised to ``<stem>.assembly.json`` in the bundle and embedded in ``<stem>.viewer.glb``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from bevel_cad.config.loader import ConfigError
from bevel_cad.config.schema import parse_color
from bevel_cad.render.colors import iter_assembly_leaf_solids, palette_rgba, rgb_to_hex
from bevel_cad.render.naming import name_from_target
from bevel_cad.render.planner import first_preview_settings

MANIFEST_SCHEMA = 1
COLOR_MODES = ("auto", "manual", "off")
DEFAULT_BASE_RGB = (0.7, 0.7, 0.7)
# YAML reads ``mode: off`` / ``mode: on`` as booleans; map them back to the intended modes.
_MODE_ALIASES = {"false": "off", "no": "off", "none": "off", "true": "auto", "yes": "auto", "on": "auto"}


@dataclass(frozen=True)
class PartEntry:
    """One named body of the assembly. ``shape`` is a located ``cq.Shape`` or a ``trimesh.Trimesh``."""

    name: str
    shape: Any
    color: Optional[str]  # "#rrggbb" or None (viewer default face colour)
    tags: Tuple[str, ...] = ()
    is_mesh: bool = False


@dataclass(frozen=True)
class AssemblyManifest:
    name: str
    parts: Tuple[PartEntry, ...]
    tags: Tuple[str, ...] = ()

    @property
    def part_names(self) -> List[str]:
        return [p.name for p in self.parts]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": MANIFEST_SCHEMA,
            "name": self.name,
            "tags": list(self.tags),
            "parts": [
                {"name": p.name, "index": i, "color": p.color, "tags": list(p.tags)}
                for i, p in enumerate(self.parts)
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AssemblyManifest":
        """Rebuild from ``to_dict()`` output (shapes are not stored; ``shape`` is ``None``)."""
        parts = tuple(
            PartEntry(name=str(p["name"]), shape=None, color=p.get("color"), tags=tuple(p.get("tags") or ()))
            for p in data.get("parts") or []
        )
        if not parts:
            raise ValueError("assembly manifest has no parts")
        return cls(name=str(data["name"]), parts=parts, tags=tuple(data.get("tags") or ()))


def _color_hex(spec: Any, *, where: str) -> str:
    try:
        return rgb_to_hex(parse_color(spec))
    except Exception as exc:
        raise ConfigError(f"{where}: invalid colour {spec!r} ({exc})") from exc


def palette_base_rgb(cfg: Any) -> Tuple[float, float, float]:
    """``viewer.colors.base`` > first preview job colour > neutral grey."""
    base = cfg.viewer.colors.base
    if base not in (None, ""):
        return parse_color(base)
    preview = first_preview_settings(cfg)
    return preview.color_rgb if preview else DEFAULT_BASE_RGB


def resolve_part_colors(cfg: Any, names: Sequence[str]) -> List[Optional[str]]:
    """Per-part ``#rrggbb`` (or ``None``) according to ``viewer.colors``; raises ``ConfigError`` on misuse."""
    colors_cfg = cfg.viewer.colors
    raw_mode = colors_cfg.mode
    mode = "auto" if raw_mode in (None, "") else str(raw_mode).strip().lower()
    mode = _MODE_ALIASES.get(mode, mode)
    if mode not in COLOR_MODES:
        raise ConfigError(f"viewer.colors.mode must be one of {list(COLOR_MODES)} (got {mode!r})")
    overrides: Dict[str, Any] = dict(colors_cfg.parts or {})
    unknown = sorted(set(overrides) - set(names))
    if unknown:
        raise ConfigError(
            f"viewer.colors.parts names parts that do not exist: {unknown}; this render has {list(names)}"
        )
    if mode == "off":
        if overrides:
            raise ConfigError("viewer.colors.parts is set but viewer.colors.mode is 'off'")
        return [None for _ in names]
    if mode == "manual":
        missing = [n for n in names if n not in overrides]
        if missing:
            raise ConfigError(f"viewer.colors.mode is 'manual' but viewer.colors.parts lacks: {missing}")
        return [_color_hex(overrides[n], where=f"viewer.colors.parts.{n}") for n in names]
    palette = palette_rgba(palette_base_rgb(cfg), len(names))
    return [
        _color_hex(overrides[n], where=f"viewer.colors.parts.{n}") if n in overrides else rgb_to_hex(color)
        for n, color in zip(names, palette)
    ]


def part_tags(cfg: Any, name: str, index: int) -> Tuple[str, ...]:
    extra = cfg.viewer.part_tags.get(name) if cfg.viewer.part_tags else None
    return (f"body:{name}", f"index:{index}", *[str(t) for t in (extra or [])])


def assembly_tags(cfg: Any, run: Any) -> Tuple[str, ...]:
    tags: List[str] = ["bevel"]
    target = run.part_source or cfg.get("part")
    if target:
        tags.append(f"part:{name_from_target(str(target))}")
    tags.extend(str(t) for t in (cfg.viewer.tags or []))
    return tuple(tags)


def build_manifest(ctx: Any, run: Any) -> AssemblyManifest:
    """Name, colour and tag the bodies of a :class:`~bevel_cad.render.pipeline.PartArtifacts`."""
    cfg = run.cfg
    bodies: List[Tuple[str, Any, bool]]
    if ctx.is_assembly and ctx.assy is not None:
        leaves = iter_assembly_leaf_solids(ctx.assy)
        if not leaves:
            raise ValueError(f"Assembly {run.run_name!r} has no tessellatable bodies")
        bodies = [(name, shape, False) for name, shape in leaves]
    elif ctx.is_mesh and ctx.mesh is not None:
        bodies = [(run.run_name, ctx.mesh, True)]
    else:
        bodies = [(run.run_name, ctx.solid, False)]
    names = [b[0] for b in bodies]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ValueError(f"Assembly body names must be unique; duplicate: {dupes}")
    colors = resolve_part_colors(cfg, names)
    parts = tuple(
        PartEntry(name=name, shape=shape, color=color, tags=part_tags(cfg, name, i), is_mesh=is_mesh)
        for i, ((name, shape, is_mesh), color) in enumerate(zip(bodies, colors))
    )
    return AssemblyManifest(name=run.run_name, parts=parts, tags=assembly_tags(cfg, run))
