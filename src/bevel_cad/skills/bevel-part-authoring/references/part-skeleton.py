"""<one-line description shown by `bevel list`>"""

from __future__ import annotations

from typing import Any

import cadquery as cq

import bevel_cad

# All tunables, in mm, under one block named after the part.
DEFAULTS = {"mypart": {"length": 60.0, "width": 20.0, "thickness": 3.0, "hole_diameter": 4.0}}


def build_mypart(length: float, width: float, thickness: float, hole_diameter: float) -> cq.Workplane:
    """Pure geometry: validate, then build. Keep it independent of any config object."""
    if min(length, width, thickness, hole_diameter) <= 0:
        raise ValueError("all dimensions must be positive.")
    if hole_diameter >= width:
        raise ValueError("hole_diameter must be smaller than width.")
    plate = cq.Workplane("XY").box(length, width, thickness)
    return plate.faces(">Z").workplane().rarray(length - 10.0, 1, 2, 1).hole(hole_diameter)


@bevel_cad.part(defaults=DEFAULTS, description="Plate with two mounting holes")
def build(cfg: Any) -> cq.Workplane:
    p = cfg.mypart
    return build_mypart(float(p.length), float(p.width), float(p.thickness), float(p.hole_diameter))
