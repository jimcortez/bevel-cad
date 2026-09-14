"""
Engraved text plates: rounded/chamfered plates with pocketed text and matching fill bodies.

Shared by the ``button_label`` examples and the ``label`` project template.
All dimensions are millimetres. Plates are centred on X/Y with the bottom face
at Z=0 and the front (engraved) face at Z=thickness.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import cadquery as cq
from cadquery import Location
from cadquery.func import circle, clean, cut, extrude, face, fillet2D, fuse, rect, text, wire

DEFAULT_FONT = "DejaVu Sans"  # ships with most Linux distros and has U+2192 (→)

# Print-tested defaults (mm).
DEFAULT_TEXT_SIZE = 10.0  # nominal em size; renders ~11 mm tall for typical text
DEFAULT_TEXT_DEPTH = 0.8  # engraved pocket depth, deep enough to paint or fill
DEFAULT_TEXT_RAISE = 0.4  # how far the fill stands proud of the front face (compensates print shrinkage)
DEFAULT_THICKNESS = 2.0
DEFAULT_HEIGHT = 25.0
DEFAULT_MARGIN = 3.0
DEFAULT_CHAMFER = 0.8  # front (+Z) outer perimeter edges; the back stays flat
DEFAULT_CORNER_RADIUS = 4.0


@dataclass(frozen=True)
class TextPlateParts:
    """
    Two print bodies: the ``plate`` with pockets cut out, and the ``text_fill`` letters
    (filling the pockets and standing ``text_raise`` proud of the front face) so they
    can be printed in a second colour and dropped in, or sliced as a multi-material object.
    """

    plate: cq.Solid
    text_fill: cq.Shape

    def to_assembly(self, name: str = "Text Plate") -> cq.Assembly:
        assy = cq.Assembly(name=name)
        assy = assy.add(self.plate, name="plate")
        assy = assy.add(self.text_fill, name="text_fill")
        return assy


def validate_plate_args(
    *,
    thickness: float,
    height: float,
    text_size: float,
    text_depth: float,
    margin: float,
    chamfer: float,
    corner_radius: float,
    hole_diameter: Optional[float] = None,
    text_raise: float = 0.0,
) -> None:
    """Raise ``ValueError`` for geometrically impossible plate parameters."""
    if thickness <= 0:
        raise ValueError("thickness must be positive.")
    if height <= 0:
        raise ValueError("height must be positive.")
    if text_size <= 0:
        raise ValueError("text_size must be positive.")
    if margin < 0:
        raise ValueError("margin must not be negative.")
    if text_depth <= 0 or text_depth >= thickness:
        raise ValueError("text_depth must be positive and smaller than thickness.")
    if text_raise < 0:
        raise ValueError("text_raise must not be negative.")
    if chamfer < 0 or chamfer >= thickness / 2.0:
        raise ValueError("chamfer (chamfer_mm) must be non-negative and smaller than thickness / 2.")
    if corner_radius < 0 or corner_radius >= height / 2.0:
        raise ValueError("corner_radius must be non-negative and smaller than height / 2.")
    if hole_diameter is not None:
        if hole_diameter <= 0:
            raise ValueError("hole_diameter must be positive.")
        if hole_diameter >= height:
            raise ValueError("hole_diameter must be smaller than height.")


def render_text(label: str, font: str, text_size: float):
    """Planar text shape (reads correctly from +Z) plus its bounding box."""
    shape = text(label, text_size, font=font)
    bb = shape.BoundingBox()
    if bb.xlen <= 0 or bb.ylen <= 0:
        raise RuntimeError(
            f"font '{font}' produced empty text geometry for {label!r}; check the font name and glyph coverage."
        )
    return shape, bb


def base_plate(width: float, height: float, thickness: float, corner_radius: float, chamfer: float) -> cq.Solid:
    """Rounded-rect plate centred on X/Y, bottom at Z=0, front (+Z) perimeter chamfered, back flat."""
    prof = face(rect(width, height))
    if corner_radius > 0:
        prof = fillet2D(prof, prof.vertices(), corner_radius)
    plate = extrude(prof, (0, 0, thickness))
    # Chamfer before any cuts so the top face contains only the outer perimeter;
    # cutting afterwards leaves hole rims and pocket walls crisp.
    if chamfer > 0:
        wp = cq.Workplane("XY").add(plate)
        plate = wp.faces(">Z").edges().chamfer(chamfer).val()
    return plate


def cut_hole(plate, cx: float, cy: float, diameter: float, thickness: float):
    """Through-hole of ``diameter`` centred at (cx, cy)."""
    hole = extrude(face(wire(circle(diameter / 2.0))), (0, 0, thickness))
    return cut(plate, hole.moved(Location((cx, cy, 0))))


def engrave(plate, shape, bb, cx: float, cy: float, thickness: float, depth: float, raise_mm: float = 0.0):
    """
    Sink ``shape`` into the top face, centred (by bounding box) at (cx, cy).

    Returns ``(plate_with_pocket, fill)`` where ``fill`` is the letters: the pocket
    volume plus ``raise_mm`` standing proud of the front face.
    """
    # The text bbox is not centred at the origin even with centred alignment,
    # so recentre via the bbox midpoint before placing.
    text_cx = 0.5 * (bb.xmin + bb.xmax)
    text_cy = 0.5 * (bb.ymin + bb.ymax)
    shape_top = shape.moved(Location((cx - text_cx, cy - text_cy, thickness)))
    pocket = extrude(shape_top, (0, 0, -depth))
    shape_bottom = shape_top.moved(Location((0, 0, -depth)))
    fill = extrude(shape_bottom, (0, 0, depth + raise_mm))
    return cut(plate, pocket), fill


def merge_fills(fills: List) -> cq.Shape:
    """Combine per-text fill solids into one shape (letters stay separate solids)."""
    if not fills:
        raise RuntimeError("No text fill geometry was produced.")
    return clean(fills[0]) if len(fills) == 1 else clean(fuse(*fills))


def build_text_plate(
    label: str,
    *,
    font: str = DEFAULT_FONT,
    text_size: float = DEFAULT_TEXT_SIZE,
    text_depth: float = DEFAULT_TEXT_DEPTH,
    text_raise: float = DEFAULT_TEXT_RAISE,
    thickness: float = DEFAULT_THICKNESS,
    height: float = DEFAULT_HEIGHT,
    margin: float = DEFAULT_MARGIN,
    chamfer: float = DEFAULT_CHAMFER,
    corner_radius: float = DEFAULT_CORNER_RADIUS,
) -> TextPlateParts:
    """
    A plain engraved label: one line of text pocketed into a plate whose width is
    derived from the rendered text width plus margins.
    """
    validate_plate_args(
        thickness=thickness, height=height, text_size=text_size, text_depth=text_depth,
        margin=margin, chamfer=chamfer, corner_radius=corner_radius, text_raise=text_raise,
    )
    if not label.strip():
        raise ValueError("label must be non-empty.")
    shape, bb = render_text(label, font, text_size)
    if bb.ylen > height - 2.0 * margin:
        raise ValueError(f"text_size too large: {label!r} does not fit within height minus margins.")
    width = bb.xlen + 2.0 * margin
    plate = base_plate(width, height, thickness, corner_radius, chamfer)
    plate, fill = engrave(plate, shape, bb, 0.0, 0.0, thickness, text_depth, text_raise)
    return TextPlateParts(plate=clean(plate), text_fill=merge_fills([fill]))
