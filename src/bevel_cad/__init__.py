"""bevel-cad: render, export, and configure CadQuery parts."""

from __future__ import annotations

try:
    from bevel_cad._version import __version__
except ImportError:  # pragma: no cover - source checkout without a build/install step
    try:
        from importlib.metadata import version as _dist_version

        __version__ = _dist_version("bevel-cad")
    except Exception:
        __version__ = "0.0.0+unknown"

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
