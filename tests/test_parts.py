"""Part target resolution and the @part decorator."""

from __future__ import annotations

import pytest
from omegaconf import OmegaConf

import bevel_cad
from bevel_cad.config import ProjectLayout
from bevel_cad.parts import InvalidPart, PartNotFound, iter_registered_parts, load_target, spec_from_callable
from tests.conftest import FIXTURES


def test_file_target_and_defaults():
    spec = load_target(str(FIXTURES / "box_part.py"))
    assert spec.name == "box_part" and spec.source.startswith("file:")
    assert spec.path == (FIXTURES / "box_part.py").resolve()
    assert spec.defaults == {} and spec.description.startswith("Minimal file-target part")
    geom = spec.build(OmegaConf.create({"size": 2.0}))
    assert geom.Volume() == pytest.approx(8.0)


def test_decorator_metadata():
    @bevel_cad.part(name="widget", defaults={"widget": {"size": 3}}, description="A widget")
    def build(cfg):
        return cfg

    spec = spec_from_callable(build, name="ignored", source="module:x")
    assert spec.name == "widget" and spec.defaults == {"widget": {"size": 3}} and spec.description == "A widget"
    d = spec.to_dict()
    assert d["defaults"] == {"widget": {"size": 3}} and d["schema"] is None


def test_module_target_with_callable(tmp_path, monkeypatch):
    pkg = tmp_path / "mypkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "shapes.py").write_text(
        "from cadquery.func import box\n"
        "def build(cfg):\n    return box(1, 1, 1)\n"
        "def other(cfg):\n    return box(2, 2, 2)\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    assert load_target("mypkg.shapes").name == "shapes"
    spec = load_target("mypkg.shapes:other")
    assert spec.name == "other" and spec.build(None).Volume() == pytest.approx(8.0)
    with pytest.raises(InvalidPart, match="no attribute"):
        load_target("mypkg.shapes:missing")


def test_project_layout_target_and_sibling_import(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "helper.py").write_text("SIZE = 4.0\n")
    (src / "thing.py").write_text("from cadquery.func import box\nimport helper\n\ndef build(cfg):\n    return box(helper.SIZE, 1, 1)\n")
    layout = ProjectLayout.from_config(tmp_path, OmegaConf.create({"project": {"configs_dir": "configs", "src_dir": "src"}}))
    spec = load_target("thing", layout=layout)
    assert spec.build(None).Volume() == pytest.approx(4.0)
    names = [r.name for r in iter_registered_parts(layout) if r.kind == "project"]
    assert names == ["helper", "thing"]


def test_unknown_target_lists_available():
    with pytest.raises(PartNotFound, match="Unknown part target 'nope_nothing'"):
        load_target("nope_nothing")


def test_module_without_build_is_invalid(tmp_path):
    f = tmp_path / "nobuild.py"
    f.write_text("x = 1\n")
    with pytest.raises(InvalidPart, match="has no build"):
        load_target(str(f))


def test_broken_provider_raises(monkeypatch):
    from bevel_cad import parts

    class _EP:
        name, value = "broken", "nosuch.module:parts"

        def load(self):
            raise ImportError("boom")

    monkeypatch.setattr(parts, "entry_points", lambda group: [_EP()] if group == parts.PROVIDER_GROUP else [])
    with pytest.raises(parts.InvalidPart, match="provider 'broken'"):
        parts.iter_registered_parts()
