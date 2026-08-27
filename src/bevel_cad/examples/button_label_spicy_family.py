"""Button label with the hole in the middle: "spicy" on the left, "family" on the right."""

from __future__ import annotations

from typing import Any

import cadquery as cq

import bevel_cad
from bevel_cad.examples.button_label import DEFAULTS, build_from_params, params_from_config

LEFT_TEXT = "spicy"
RIGHT_TEXT = "family"

_DEFAULTS = {"button_label": {**DEFAULTS["button_label"], "left_text": LEFT_TEXT, "right_text": RIGHT_TEXT}}


@bevel_cad.part(defaults=_DEFAULTS, description="'spicy | family' button label")
def build(cfg: Any) -> cq.Assembly:
    return build_from_params(params_from_config(cfg)).to_assembly("Spicy Family Label")
