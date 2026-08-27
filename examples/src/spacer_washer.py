"""
Spacer washer: a thick, filleted standoff ring. Dimensions are given in inches in the ``spacer_washer``
block (the geometry itself is built in mm)::

    spacer_washer:
      outer_diameter_in: 1.75
      height_in: 0.25
      hole_diameter_in: 0.25
      fillet_mm: 0.75
"""

from __future__ import annotations

from typing import Any

import cadquery as cq
from cadquery import Location
from cadquery.func import circle, extrude, face, wire

import bevel_cad

MM_PER_IN = 25.4

DEFAULTS = {
    "spacer_washer": {"outer_diameter_in": 1.75, "height_in": 0.25, "hole_diameter_in": 0.25, "fillet_mm": 0.75}
}


def build_spacer_washer(
    outer_diameter_in: float = 1.75,
    height_in: float = 0.25,
    hole_diameter_in: float = 0.25,
    fillet_mm: float = 0.75,
) -> cq.Solid:
    """Washer-like spacer, axis +Z, centred about Z=0."""
    outer_r = 0.5 * float(outer_diameter_in) * MM_PER_IN
    inner_r = 0.5 * float(hole_diameter_in) * MM_PER_IN
    height_mm = float(height_in) * MM_PER_IN
    if inner_r <= 0 or outer_r <= 0:
        raise ValueError("Radii must be positive.")
    if inner_r >= outer_r:
        raise ValueError("Hole radius must be smaller than outer radius.")
    if height_mm <= 0:
        raise ValueError("Height must be positive.")

    ring_face = face(wire(circle(outer_r)), wire(circle(inner_r)))
    solid = extrude(ring_face, (0, 0, height_mm)).moved(Location((0, 0, -height_mm / 2.0)))
    f = float(max(0.0, fillet_mm))
    if f > 0:
        solid = cq.Workplane("XY").add(solid).faces(">Z or <Z").edges().fillet(f).val()
    return solid


@bevel_cad.part(defaults=DEFAULTS, description="Spacer washer / standoff (inch dimensions, filleted edges)")
def build(cfg: Any) -> cq.Solid:
    p = cfg.spacer_washer
    return build_spacer_washer(p.outer_diameter_in, p.height_in, p.hole_diameter_in, p.fillet_mm)
