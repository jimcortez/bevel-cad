"""
Typed configuration schema (OmegaConf structured configs).

Only the blocks bevel-cad itself understands are typed -- ``project``,
``rendering`` and ``viewer``.  Everything else in a config is free-form so
parts can declare whatever keys they need.  Downstream projects extend
:class:`BevelSchema` with their own dataclass to get strict validation of
their own blocks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

__all__ = [
    "JOB_SETTINGS_TYPES",
    "BevelSchema",
    "ObjSettings",
    "PreviewSettings",
    "ProjectConfig",
    "RenderingConfig",
    "StepSettings",
    "StlSettings",
    "ViewerConfig",
    "ViewerStyle",
    "parse_color",
]

RGB = Tuple[float, float, float]


def parse_color(spec: Any) -> RGB:
    """Accept ``#rrggbb``, CSS colour names, or an RGB triple (0-1 floats or 0-255 ints)."""
    if isinstance(spec, (list, tuple)) and len(spec) >= 3:
        vals = [float(v) for v in spec[:3]]
        if any(v > 1.0 for v in vals):
            vals = [v / 255.0 for v in vals]
        return (vals[0], vals[1], vals[2])
    from PIL import ImageColor

    r, g, b = ImageColor.getrgb(str(spec).strip())[:3]
    return (r / 255.0, g / 255.0, b / 255.0)


# --- per-export-format job settings -------------------------------------------------------


@dataclass
class StlSettings:
    stl_ascii: bool = False


@dataclass
class StepSettings:
    write_pcurves: bool = True
    precision_mode: int = 0


@dataclass
class ObjSettings:
    unit_scale_mm_to_m: bool = True
    target_face_count: Optional[int] = None
    watertight_required: bool = False


@dataclass
class PreviewSettings:
    image_width: int = 800
    image_height: int = 600
    elevation: float = 30.0
    azimuth: float = 45.0
    roll: float = 0.0
    light_azimuth: float = 225.0
    light_elevation: float = 45.0
    opacity: float = 1.0
    color: Any = "#b3b3b3"
    background: Any = "#1a1a2e"

    @property
    def color_rgb(self) -> RGB:
        return parse_color(self.color)

    @property
    def background_rgb(self) -> RGB:
        return parse_color(self.background)


JOB_SETTINGS_TYPES: Dict[str, type] = {
    "stl": StlSettings,
    "step": StepSettings,
    "obj": ObjSettings,
    "preview": PreviewSettings,
}


# --- typed blocks ---------------------------------------------------------------------------


@dataclass
class ViewerStyle:
    """Styling forwarded to cadquery-web-viewer via ``CADQUERY_WEB_VIEWER_*`` env vars."""

    protocol: Optional[str] = None
    texture: Optional[str] = None
    color_faces: Optional[str] = None
    color_edges: Optional[str] = None
    color_vertices: Optional[str] = None


@dataclass
class ViewerConfig:
    """Connection to a running ``cadquery-web-viewer`` (remote mode)."""

    enabled: bool = False
    host: str = "localhost"
    port: int = 32323
    upload_timeout: float = 300.0
    post_timeout: float = 60.0
    tolerance: float = 0.05
    angular_tolerance: float = 0.1
    style: ViewerStyle = field(default_factory=ViewerStyle)


@dataclass
class RenderingConfig:
    """Where bundles go, tessellation tolerances, and the export job table."""

    name: Optional[str] = None
    output_dir: str = "renders"
    tolerance: float = 0.001
    angular_tolerance: float = 0.05
    # job name -> {format?, enabled?, filename?, <per-format settings>}
    exports: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectConfig:
    """Layout of a bevel project (see ``bevel_cad.config.paths``)."""

    name: Optional[str] = None
    description: Optional[str] = None
    configs_dir: Any = "configs"  # str or list[str]
    src_dir: Optional[str] = "src"  # null: no project source files (parts come from entry points / providers)
    hooks: Optional[str] = None  # "package.module:ATTR" -> bevel_cad.commands.Hooks (see load_project_hooks)


@dataclass
class BevelSchema:
    """Root schema. Extra top-level keys are allowed (open config)."""

    part: Optional[str] = None
    name: Optional[str] = None
    project: ProjectConfig = field(default_factory=ProjectConfig)
    rendering: RenderingConfig = field(default_factory=RenderingConfig)
    viewer: ViewerConfig = field(default_factory=ViewerConfig)
