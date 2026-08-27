"""Tall, skinny "POWER" badge: hole on top, one upright letter per row beneath it."""

from __future__ import annotations

from typing import Any

import cadquery as cq

import bevel_cad
from bevel_cad.examples.button_label import DEFAULTS, build_from_params, params_from_config

STACKED_TEXT = "POWER"

_DEFAULTS = {"button_label": {**DEFAULTS["button_label"], "layout": "stacked", "stacked_text": STACKED_TEXT}}


@bevel_cad.part(defaults=_DEFAULTS, description="Stacked POWER button label")
def build(cfg: Any) -> cq.Assembly:
    return build_from_params(params_from_config(cfg)).to_assembly("Power Label")
