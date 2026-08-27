"""
Snap-in button label: a badge plate with a through-hole for the button and
engraved text pockets, plus matching ``text_fill`` bodies for two-colour printing.

Config block ``button_label`` (all mm)::

    button_label:
      layout: horizontal        # or "stacked": hole on top, one letter per row below
      left_text: "Free →"
      right_text: ""
      stacked_text: "POWER"     # used by the stacked layout
      font: DejaVu Sans
      text_size: 10.0
      text_depth: 0.8
      text_raise: 0.4           # fill stands proud of the face (compensates print shrinkage)
      thickness: 2.0
      height: 25.0              # narrow plate dimension (width for the stacked layout)
      hole_diameter: 20.0
      margin: 3.0
      chamfer: 0.8
      corner_radius: 4.0
      letter_gap: 2.0
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Tuple

import cadquery as cq
from cadquery.func import clean

import bevel_cad
from bevel_cad.geom.text_plate import (
    DEFAULT_CHAMFER,
    DEFAULT_CORNER_RADIUS,
    DEFAULT_FONT,
    DEFAULT_HEIGHT,
    DEFAULT_MARGIN,
    DEFAULT_TEXT_DEPTH,
    DEFAULT_TEXT_RAISE,
    DEFAULT_TEXT_SIZE,
    DEFAULT_THICKNESS,
    TextPlateParts,
    base_plate,
    cut_hole,
    engrave,
    merge_fills,
    render_text,
    validate_plate_args,
)


@dataclass
class ButtonLabelParams:
    layout: str = "horizontal"
    left_text: str = "Free →"
    right_text: str = ""
    stacked_text: str = "POWER"
    font: str = DEFAULT_FONT
    text_size: float = DEFAULT_TEXT_SIZE
    text_depth: float = DEFAULT_TEXT_DEPTH
    text_raise: float = DEFAULT_TEXT_RAISE
    thickness: float = DEFAULT_THICKNESS
    height: float = DEFAULT_HEIGHT
    hole_diameter: float = 20.0
    margin: float = DEFAULT_MARGIN
    chamfer: float = DEFAULT_CHAMFER
    corner_radius: float = DEFAULT_CORNER_RADIUS
    letter_gap: float = 2.0


DEFAULTS: Dict[str, Any] = {"button_label": asdict(ButtonLabelParams())}


class ButtonLabelParts(TextPlateParts):
    def to_assembly(self, name: str = "Button Label") -> cq.Assembly:
        return super().to_assembly(name)


# --- horizontal layout: [left text] [hole] [right text] -----------------------


def build_button_label(
    left_text: str = ButtonLabelParams.left_text,
    right_text: str = ButtonLabelParams.right_text,
    font: str = DEFAULT_FONT,
    text_size: float = ButtonLabelParams.text_size,
    text_depth: float = ButtonLabelParams.text_depth,
    text_raise: float = ButtonLabelParams.text_raise,
    thickness: float = ButtonLabelParams.thickness,
    height: float = ButtonLabelParams.height,
    hole_diameter: float = ButtonLabelParams.hole_diameter,
    margin: float = ButtonLabelParams.margin,
    chamfer_mm: float = ButtonLabelParams.chamfer,
    corner_radius: float = ButtonLabelParams.corner_radius,
) -> ButtonLabelParts:
    """
    Layout (X axis, left to right): [left text] [hole] [right text]; every element
    carries ``margin`` on each side, so the plate width is derived from the rendered
    text widths. Either text may be empty (but not both).
    """
    validate_plate_args(
        thickness=thickness, height=height, text_size=text_size, text_depth=text_depth, margin=margin,
        chamfer=chamfer_mm, corner_radius=corner_radius, hole_diameter=hole_diameter, text_raise=text_raise,
    )
    if not left_text.strip() and not right_text.strip():
        raise ValueError("At least one of left_text / right_text must be non-empty.")

    def render(label: str):
        if not label.strip():
            return None
        shape, bb = render_text(label, font, text_size)
        if bb.ylen > height - 2.0 * margin:
            raise ValueError(f"text_size too large: {label!r} does not fit within height minus margins.")
        return shape, bb

    left = render(left_text)
    right = render(right_text)

    elements: List[Tuple[str, float]] = []
    if left is not None:
        elements.append(("left", left[1].xlen))
    elements.append(("hole", hole_diameter))
    if right is not None:
        elements.append(("right", right[1].xlen))
    plate_width = sum(w for _, w in elements) + 2.0 * margin * len(elements)

    centers: Dict[str, float] = {}
    x = -plate_width / 2.0
    for kind, w in elements:
        x += margin
        centers[kind] = x + w / 2.0
        x += w + margin

    plate = base_plate(plate_width, height, thickness, corner_radius, chamfer_mm)
    plate = cut_hole(plate, centers["hole"], 0.0, hole_diameter, thickness)
    fills = []
    for kind, rendered in (("left", left), ("right", right)):
        if rendered is not None:
            plate, fill = engrave(plate, *rendered, centers[kind], 0.0, thickness, text_depth, text_raise)
            fills.append(fill)
    return ButtonLabelParts(plate=clean(plate), text_fill=merge_fills(fills))


# --- stacked layout: hole on top, one upright letter per row beneath it -------


def build_stacked_button_label(
    stacked_text: str,
    font: str = DEFAULT_FONT,
    text_size: float = ButtonLabelParams.text_size,
    text_depth: float = ButtonLabelParams.text_depth,
    text_raise: float = ButtonLabelParams.text_raise,
    thickness: float = ButtonLabelParams.thickness,
    width: float = ButtonLabelParams.height,
    hole_diameter: float = ButtonLabelParams.hole_diameter,
    margin: float = ButtonLabelParams.margin,
    letter_gap: float = ButtonLabelParams.letter_gap,
    chamfer_mm: float = ButtonLabelParams.chamfer,
    corner_radius: float = ButtonLabelParams.corner_radius,
) -> ButtonLabelParts:
    """
    Tall, skinny badge: the hole at the top and the text beneath it, one upright letter
    per row on a uniform pitch (tallest glyph + ``letter_gap``). ``width`` is the narrow
    (X) dimension of the plate.
    """
    validate_plate_args(
        thickness=thickness, height=width, text_size=text_size, text_depth=text_depth, margin=margin,
        chamfer=chamfer_mm, corner_radius=corner_radius, hole_diameter=hole_diameter, text_raise=text_raise,
    )
    if letter_gap < 0:
        raise ValueError("letter_gap must not be negative.")
    letters = [ch for ch in stacked_text if not ch.isspace()]
    if not letters:
        raise ValueError("stacked_text must contain at least one non-space character.")

    rendered = [render_text(ch, font, text_size) for ch in letters]
    max_w = max(bb.xlen for _, bb in rendered)
    max_h = max(bb.ylen for _, bb in rendered)
    if max_w > width - 2.0 * margin:
        raise ValueError("text_size too large: widest letter does not fit within width minus margins.")

    pitch = max_h + letter_gap
    column_h = len(letters) * max_h + (len(letters) - 1) * letter_gap
    plate_len = 4.0 * margin + hole_diameter + column_h
    hole_cy = plate_len / 2.0 - margin - hole_diameter / 2.0
    column_top = hole_cy - hole_diameter / 2.0 - 2.0 * margin

    plate = base_plate(width, plate_len, thickness, corner_radius, chamfer_mm)
    plate = cut_hole(plate, 0.0, hole_cy, hole_diameter, thickness)
    fills = []
    for i, (shape, bb) in enumerate(rendered):
        row_cy = column_top - max_h / 2.0 - i * pitch
        plate, fill = engrave(plate, shape, bb, 0.0, row_cy, thickness, text_depth, text_raise)
        fills.append(fill)
    return ButtonLabelParts(plate=clean(plate), text_fill=merge_fills(fills))


def build_from_params(p: ButtonLabelParams) -> ButtonLabelParts:
    if str(p.layout).lower() == "stacked":
        return build_stacked_button_label(
            p.stacked_text, font=p.font, text_size=p.text_size, text_depth=p.text_depth, text_raise=p.text_raise,
            thickness=p.thickness,
            width=p.height, hole_diameter=p.hole_diameter, margin=p.margin, letter_gap=p.letter_gap,
            chamfer_mm=p.chamfer, corner_radius=p.corner_radius,
        )
    return build_button_label(
        left_text=p.left_text, right_text=p.right_text, font=p.font, text_size=p.text_size, text_depth=p.text_depth,
        text_raise=p.text_raise, thickness=p.thickness, height=p.height, hole_diameter=p.hole_diameter, margin=p.margin,
        chamfer_mm=p.chamfer, corner_radius=p.corner_radius,
    )


def params_from_config(cfg: Any) -> ButtonLabelParams:
    block = cfg.get("button_label") if hasattr(cfg, "get") else None
    kwargs = {}
    for f in ButtonLabelParams.__dataclass_fields__:
        if block is not None and f in block:
            kwargs[f] = block[f]
    return ButtonLabelParams(**kwargs)


@bevel_cad.part(defaults=DEFAULTS, description="Button badge with a hole and engraved text; two bodies (plate, text_fill)")
def build(cfg: Any) -> cq.Assembly:
    return build_from_params(params_from_config(cfg)).to_assembly()
