"""Tests for run-name slugs, bundle stems, and filename templates."""

from __future__ import annotations

from datetime import datetime

from bevel_cad.render.naming import body_slug, render_bundle_stem, resolve_filename_template, slugify


def test_render_bundle_stem():
    stem = render_bundle_stem("Trefoil Knot", now=datetime(2025, 6, 7, 14, 30, 22))
    assert stem == "trefoil-knot_20250607-143022"


def test_render_bundle_stem_empty_name_falls_back_to_part():
    assert render_bundle_stem("", now=datetime(2025, 1, 1, 0, 0, 0)) == "part_20250101-000000"


def test_slugify():
    assert slugify("  Hello, World! ") == "hello-world"


def test_body_slug_keeps_case_and_underscores():
    assert body_slug("text fill") == "text-fill"
    assert body_slug("Text_Fill") == "Text_Fill"
    assert body_slug("") == "body"


def test_resolve_filename_template():
    name = resolve_filename_template(
        "{run_name}-{name}.png", bundle_stem="rod_20250101-120000", run_name="Rod"
    )
    assert name == "Rod-rod_20250101-120000.png"
