"""Minimal file-target part used by the tests."""

from cadquery.func import box


def build(cfg):
    size = float(cfg.get("size", 10.0))
    return box(size, size, size)
