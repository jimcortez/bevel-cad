"""Config layering, normalisation, and project discovery."""

from __future__ import annotations

from pathlib import Path

import pytest
from omegaconf import OmegaConf

from bevel_cad.config import ConfigError, ProjectLayout, find_project_root, load_layers, normalize_layer


def _write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_layer_order_project_lt_file_lt_dotlist(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / "bevel.yaml", "rendering:\n  name: from-project\nwidget:\n  size: 1\n  color: red\n")
    f = _write(tmp_path / "configs" / "a.yaml", "rendering:\n  name: from-file\nwidget:\n  size: 2\n")
    lc = load_layers(files=[f], dotlist=["widget.size=3"], user_config=False)
    assert lc.root == tmp_path.resolve()
    assert lc.cfg.rendering.name == "from-file"
    assert lc.cfg.widget.size == 3
    assert lc.cfg.widget.color == "red"
    assert [s.layer for s in lc.sources] == ["defaults", "project", "file", "dotlist"]
    assert lc.layout is not None and lc.layout.configs_dirs == (tmp_path.resolve() / "configs",)


def test_local_layer_and_part_defaults_position(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / "bevel.yaml", "widget: {size: 1}\n")
    _write(tmp_path / "bevel.local.yaml", "widget: {size: 2}\n")
    f = _write(tmp_path / "f.yaml", "widget: {size: 4}\n")
    lc = load_layers(part_defaults={"widget": {"size": 3, "depth": 9}}, user_config=False)
    assert lc.cfg.widget.size == 3  # part defaults beat project/local
    lc = load_layers(files=[f], part_defaults={"widget": {"size": 3}}, user_config=False)
    assert lc.cfg.widget.size == 4  # explicit files beat part defaults
    assert [s.layer for s in lc.sources] == ["defaults", "project", "local", "part", "file"]


def test_struct_missing_key_raises_and_get_defaults(cfg):
    with pytest.raises(AttributeError):
        _ = cfg.nope
    assert cfg.get("nope", 5) == 5
    assert getattr(cfg, "nope", "d") == "d"


def test_typed_validation_error(tmp_path):
    with pytest.raises(ConfigError):
        load_layers(project_config=None, user_config=False, dotlist=["viewer.port=notanint"])
    with pytest.raises(ConfigError):
        load_layers(project_config=None, user_config=False, overrides={"rendering": {"unknown_key": 1}})


def test_server_block_is_rejected():
    with pytest.raises(ConfigError, match="renamed 'viewer:'"):
        normalize_layer({"server": {"viewer": {"host": "h"}}}, source="x.yaml")


def test_list_form_exports_are_rejected(tmp_path):
    f = _write(tmp_path / "old.yaml", "rendering:\n  exports:\n    - format: glb\n      enabled: false\n")
    with pytest.raises(ConfigError, match="rendering.exports must be a mapping"):
        load_layers(files=[f], project_config=None, user_config=False)


def test_unknown_export_job_key_is_rejected(tmp_path):
    f = _write(tmp_path / "odd.yaml", "rendering:\n  exports:\n    stl:\n      stl_cache: yes\n")
    from bevel_cad.render.pipeline import start_run
    from bevel_cad.render.planner import RenderPlanner

    lc = load_layers(files=[f], project_config=None, user_config=False)
    with pytest.raises(Exception, match="stl_cache"):
        RenderPlanner.from_run(start_run(lc.cfg, root=tmp_path))


def test_explicit_project_config_uses_bevel_local_sibling(tmp_path):
    p = _write(tmp_path / "custom.yaml", "widget: {a: 1}\n")
    _write(tmp_path / "custom.local.yaml", "widget: {a: 3}\n")  # not a recognised local file
    _write(tmp_path / "bevel.local.yaml", "widget: {a: 2}\n")
    lc = load_layers(project_config=p, user_config=False)
    assert lc.cfg.widget.a == 2
    assert lc.root == tmp_path.resolve()


def test_find_project_root_walks_up_and_env(tmp_path, monkeypatch):
    _write(tmp_path / "bevel.yaml", "")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert find_project_root(nested) == tmp_path.resolve()
    monkeypatch.setenv("BEVEL_ROOT", str(tmp_path / "a"))
    assert find_project_root(nested) == (tmp_path / "a").resolve()
    monkeypatch.delenv("BEVEL_ROOT")
    assert find_project_root(Path("/")) is None


def test_layout_lookup(tmp_path):
    _write(tmp_path / "configs" / "foo.yaml", "")
    _write(tmp_path / "src" / "foo.py", "")
    _write(tmp_path / "src" / "_helper.py", "")
    cfg = OmegaConf.create({"project": {"configs_dir": ["configs", "more"], "src_dir": "src"}, "rendering": {"output_dir": "out"}})
    layout = ProjectLayout.from_config(tmp_path, cfg)
    assert layout.config_file_for("foo") == tmp_path.resolve() / "configs" / "foo.yaml"
    assert layout.config_file_for("bar") is None
    assert layout.source_file_for("foo") == tmp_path.resolve() / "src" / "foo.py"
    assert layout.iter_source_names() == ("foo",)
    assert layout.renders_dir == tmp_path.resolve() / "out"
