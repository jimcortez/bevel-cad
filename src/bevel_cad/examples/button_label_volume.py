"""Small volume-button badge: "Volume" on the left, a 7 mm hole on the right."""

from __future__ import annotations

from typing import Any

import cadquery as cq

import bevel_cad
from bevel_cad.examples.button_label import DEFAULTS, build_from_params, params_from_config

LEFT_TEXT = "Volume"
RIGHT_TEXT = ""
TEXT_SIZE_MM = 5.0
HOLE_DIAMETER_MM = 7.0

_DEFAULTS = {
    "button_label": {
        **DEFAULTS["button_label"],
        "left_text": LEFT_TEXT,
        "right_text": RIGHT_TEXT,
        "text_size": TEXT_SIZE_MM,
        "hole_diameter": HOLE_DIAMETER_MM,
    }
}


@bevel_cad.part(defaults=_DEFAULTS, description="Volume button label with a 7 mm hole")
def build(cfg: Any) -> cq.Assembly:
    return build_from_params(params_from_config(cfg)).to_assembly("Volume Label")
