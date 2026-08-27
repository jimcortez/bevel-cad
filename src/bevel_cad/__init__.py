"""bevel-cad: render, export, and configure CadQuery parts."""

from __future__ import annotations

__version__ = "0.1.0"

from bevel_cad.config import BevelSchema, load_config, load_layers  # noqa: E402
from bevel_cad.parts import PartSpec, load_target, part  # noqa: E402
from bevel_cad.render.pipeline import RenderResult, RunContext, render_part, start_run  # noqa: E402

__all__ = [
    "__version__",
    "BevelSchema",
    "PartSpec",
    "RenderResult",
    "RunContext",
    "load_config",
    "load_layers",
    "load_target",
    "part",
    "render_part",
    "start_run",
]
