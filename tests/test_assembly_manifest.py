"""Tests for the viewer assembly manifest: part naming, colours and tags."""

from __future__ import annotations

from datetime import datetime

import cadquery as cq
import pytest
import trimesh
from cadquery.func import box

from bevel_cad.config import load_layers
from bevel_cad.config.loader import ConfigError
from bevel_cad.render.assembly import AssemblyManifest, build_manifest, resolve_part_colors
from bevel_cad.render.pipeline import PartArtifacts, start_run


def _cfg(tmp_path, monkeypatch, *dotlist):
    monkeypatch.chdir(tmp_path)
    return load_layers(project_config=None, user_config=False, dotlist=list(dotlist)).cfg


def _pair():
    return cq.Assembly(name="A").add(box(1, 1, 1), name="a").add(box(1, 1, 1).moved(cq.Location((3, 0, 0))), name="b")


def _manifest(tmp_path, monkeypatch, part, *dotlist, name="run", part_source=None):
    cfg = _cfg(tmp_path, monkeypatch, *dotlist)
    run = start_run(cfg, name=name, now=datetime(2025, 1, 1), part_source=part_source)
    return build_manifest(PartArtifacts(part, run), run)


def test_auto_palette_gives_distinct_hex_colors(tmp_path, monkeypatch):
    m = _manifest(tmp_path, monkeypatch, _pair())
    assert m.name == "run" and m.part_names == ["a", "b"]
    colors = [p.color for p in m.parts]
    assert all(c is not None and c.startswith("#") and len(c) == 7 for c in colors)
    assert len(set(colors)) == 2


def test_auto_palette_respects_single_override(tmp_path, monkeypatch):
    # dotlist values are YAML: quote hex colours so '#' is not read as a comment
    m = _manifest(tmp_path, monkeypatch, _pair(), 'viewer.colors.parts.a="#ff0000"')
    assert m.parts[0].color == "#ff0000"
    assert m.parts[1].color not in (None, "#ff0000")


def test_manual_mode_requires_every_part(tmp_path, monkeypatch):
    m = _manifest(tmp_path, monkeypatch, _pair(), "viewer.colors.mode=manual",
                  'viewer.colors.parts.a="#ff0000"', "viewer.colors.parts.b=blue")
    assert [p.color for p in m.parts] == ["#ff0000", "#0000ff"]
    with pytest.raises(ConfigError, match="lacks: \\['b'\\]"):
        _manifest(tmp_path, monkeypatch, _pair(), "viewer.colors.mode=manual", 'viewer.colors.parts.a="#ff0000"')


def test_off_mode_gives_no_colors(tmp_path, monkeypatch):
    # YAML turns a bare `off` into False; both spellings must work
    for spelling in ("viewer.colors.mode=off", "viewer.colors.mode='off'"):
        m = _manifest(tmp_path, monkeypatch, _pair(), spelling)
        assert [p.color for p in m.parts] == [None, None]
    with pytest.raises(ConfigError, match="'off'"):
        _manifest(tmp_path, monkeypatch, _pair(), "viewer.colors.mode=off", 'viewer.colors.parts.a="#ff0000"')


def test_bad_mode_unknown_part_and_bad_color_are_config_errors(tmp_path, monkeypatch):
    with pytest.raises(ConfigError, match="viewer.colors.mode"):
        _manifest(tmp_path, monkeypatch, _pair(), "viewer.colors.mode=rainbow")
    with pytest.raises(ConfigError, match="do not exist: \\['zzz'\\]"):
        _manifest(tmp_path, monkeypatch, _pair(), 'viewer.colors.parts.zzz="#ff0000"')
    with pytest.raises(ConfigError, match="invalid colour"):
        _manifest(tmp_path, monkeypatch, _pair(), "viewer.colors.parts.a=notacolour")


def test_base_color_and_preview_fallback(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch, 'viewer.colors.base="#00ff00"')
    assert resolve_part_colors(cfg, ["only"]) == ["#00ff00"]
    cfg = _cfg(tmp_path, monkeypatch, 'rendering.exports.preview.color="#123456"')
    assert resolve_part_colors(cfg, ["only"]) == ["#123456"]


def test_single_solid_and_mesh_are_one_part_named_after_run(tmp_path, monkeypatch):
    m = _manifest(tmp_path, monkeypatch, box(1, 1, 1), name="Solo Box", part_source="file:box.py")
    assert m.part_names == ["Solo Box"] and not m.parts[0].is_mesh
    assert m.parts[0].tags == ("body:Solo Box", "index:0")
    assert m.tags == ("bevel", "part:box")
    mm = _manifest(tmp_path, monkeypatch, trimesh.creation.box(extents=(1, 1, 1)), name="mesh")
    assert mm.part_names == ["mesh"] and mm.parts[0].is_mesh


def test_tags_from_config_are_appended(tmp_path, monkeypatch):
    m = _manifest(tmp_path, monkeypatch, _pair(), "viewer.tags=[rev-b, sla]", "viewer.part_tags.a=[printed]",
                  part_source="pkg.knots.k6_1")
    assert m.tags == ("bevel", "part:k6_1", "rev-b", "sla")
    assert m.parts[0].tags == ("body:a", "index:0", "printed")
    assert m.parts[1].tags == ("body:b", "index:1")


def test_leaf_bodies_are_in_world_coordinates(tmp_path, monkeypatch):
    assy = cq.Assembly(name="A").add(box(1, 1, 1), name="a", loc=cq.Location((5, 0, 0)))
    m = _manifest(tmp_path, monkeypatch, assy)
    assert m.parts[0].shape.Center().x == pytest.approx(5.0)


def test_manifest_dict_round_trip(tmp_path, monkeypatch):
    m = _manifest(tmp_path, monkeypatch, _pair(), "viewer.tags=[x]")
    d = m.to_dict()
    assert d["schema"] == 1 and d["name"] == "run" and d["tags"] == ["bevel", "x"]
    assert [p["index"] for p in d["parts"]] == [0, 1]
    back = AssemblyManifest.from_dict(d)
    assert back.part_names == m.part_names and [p.color for p in back.parts] == [p.color for p in m.parts]
    assert back.parts[0].tags == m.parts[0].tags and back.tags == m.tags
    with pytest.raises(ValueError, match="no parts"):
        AssemblyManifest.from_dict({"name": "x", "parts": []})
