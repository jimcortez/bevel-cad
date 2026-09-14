"""CLI + command layer on a scaffolded temporary project."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from bevel_cad import commands
from bevel_cad.cli import main
from tests.conftest import FIXTURES


@pytest.fixture
def project(tmp_path, monkeypatch, clean_logging):
    (tmp_path / "bevel.yaml").write_text(
        "project:\n  name: demo\nrendering:\n  exports:\n    preview: {enabled: false}\nwidget:\n  size: 5\n"
    )
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "cube.yaml").write_text("part: cube\nsize: 3\n")
    (tmp_path / "configs" / "alias.yaml").write_text("part: cube\nsize: 7\nrendering:\n  name: aliased\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "cube.py").write_text(
        "import bevel_cad\nfrom cadquery.func import box\n\n"
        "@bevel_cad.part(defaults={'size': 2, 'extra': {'depth': 1}}, description='A cube')\n"
        "def build(cfg):\n    s = float(cfg.size)\n    return box(s, s, s)\n"
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _json_out(capsys):
    return json.loads(capsys.readouterr().out)


def test_render_by_name_uses_project_config_and_part_defaults(project, capsys):
    rc = main(["render", "cube", "--json"])
    assert rc == 0
    d = _json_out(capsys)
    assert d["run_name"] == "cube"
    bundle = Path(d["bundle_dir"])
    assert bundle.parent == project / "renders"
    snap = yaml.safe_load((bundle / f"{d['stem']}.yaml").read_text())
    assert snap["size"] == 3  # configs/cube.yaml beats the part default (2)
    assert snap["extra"]["depth"] == 1  # part default survives
    assert snap["widget"]["size"] == 5  # project config survives
    assert snap["part"] == "cube"
    assert set(d["files"]) == {"stl", "glb", "config", "stats"}


def test_render_by_config_name_follows_part_key(project, capsys):
    rc = main(["render", "alias", "--skip", "glb,preview", "--json"])
    assert rc == 0
    d = _json_out(capsys)
    assert d["run_name"] == "aliased" and d["stats"]["render.part"].startswith("file:")


def test_render_yaml_target_dotlist_and_filters(project, capsys):
    rc = main(["render", "configs/alias.yaml", "size=1", "--skip", "glb", "--json"])
    assert rc == 0
    d = _json_out(capsys)
    assert d["run_name"] == "aliased" and set(d["files"]) == {"stl", "config", "stats"}
    stem = d["stem"]
    snap = yaml.safe_load((Path(d["bundle_dir"]) / f"{stem}.yaml").read_text())
    assert snap["size"] == 1


def test_render_only_and_out_and_name(project, capsys):
    rc = main(["render", "cube", "--only", "step", "--out", "elsewhere", "--name", "My Cube", "--json"])
    assert rc == 0
    d = _json_out(capsys)
    assert set(d["files"]) == {"step", "config", "stats"}
    assert Path(d["bundle_dir"]).parent == project / "elsewhere"
    assert d["stem"].startswith("my-cube_")


def test_render_file_target_outside_project(tmp_path, monkeypatch, clean_logging, capsys):
    monkeypatch.chdir(tmp_path)
    rc = main(["render", str(FIXTURES / "box_part.py"), "size=4", "rendering.exports.preview.enabled=false", "--json"])
    assert rc == 0
    d = _json_out(capsys)
    assert d["run_name"] == "box_part" and Path(d["bundle_dir"]).parent == tmp_path / "renders"


def test_render_unknown_target_exit_code(project, capsys):
    rc = main(["render", "does_not_exist"])
    assert rc == 1
    assert "Unknown part target" in capsys.readouterr().err


def test_render_bad_filter_exit_code(project, capsys):
    assert main(["render", "cube", "--skip", "dxf"]) == 1
    assert "Unknown export format" in capsys.readouterr().err


def test_config_command_shows_merged_layers(project, capsys):
    assert main(["config", "cube", "size=9"]) == 0
    out = yaml.safe_load(capsys.readouterr().out)
    assert out["size"] == 9 and out["extra"] == {"depth": 1} and out["project"]["name"] == "demo"
    assert main(["config", "--json"]) == 0
    assert _json_out(capsys)["widget"]["size"] == 5


def test_list_describe_and_project(project, capsys):
    assert main(["list", "--json"]) == 0
    items = _json_out(capsys)
    names = {i["name"]: i["kind"] for i in items}
    assert names["cube"] == "project"
    assert main(["describe", "cube", "--json"]) == 0
    info = _json_out(capsys)
    assert info["description"] == "A cube" and info["defaults"] == {"size": 2, "extra": {"depth": 1}}
    assert main(["project", "--json"]) == 0
    pi = _json_out(capsys)
    assert pi["root"] == str(project.resolve()) and pi["layout"]["src_dir"].endswith("/src")


def test_renders_show_inspect_upload(project, capsys):
    assert main(["render", "cube", "--json"]) == 0
    d = _json_out(capsys)
    assert main(["renders", "--json"]) == 0
    listed = _json_out(capsys)
    assert listed[0]["stem"] == d["stem"] and listed[0]["run_name"] == "cube"
    assert main(["show", d["stem"], "--json"]) == 0
    shown = _json_out(capsys)
    assert shown["config"]["size"] == 3 and "render.total.duration_s" in shown["stats"] and shown["log_tail"]
    assert main(["inspect", d["files"]["stl"], "--json"]) == 0
    rep = _json_out(capsys)[0]
    assert rep["watertight"] is True and rep["components"] == 1 and rep["ok"] is True
    with patch("bevel_cad.viewer.ensure_reachable"), patch("bevel_cad.viewer._show") as show:
        assert main(["upload", d["bundle_dir"], "viewer.port=4242", "--json"]) == 0
    up = _json_out(capsys)
    assert up["viewer_names"] == ["cube"] and up["viewer_url"] == "http://localhost:4242/"
    assert show.call_args[1]["remote_options"]["port"] == 4242
    assert show.call_args[0][0] == Path(d["files"]["glb"]).read_bytes()


def test_legacy_build_returning_none(project, capsys):
    (project / "src" / "legacy.py").write_text("def build(cfg):\n    return None\n")
    assert main(["render", "legacy", "--json"]) == 0
    d = _json_out(capsys)
    assert d["files"] == {} and d["bundle_dir"] is None
    assert not (project / "renders").exists()


def test_legacy_build_that_renders_itself_reports_its_bundle(project, capsys):
    (project / "src" / "selfrender.py").write_text(
        "from cadquery.func import box\nimport bevel_cad\n\n"
        "def build(cfg):\n    bevel_cad.render_part(box(1, 1, 1), cfg, name='inner')\n    return None\n"
    )
    assert main(["render", "selfrender", "--json"]) == 0
    d = _json_out(capsys)
    assert d["run_name"] == "inner" and "stl" in d["files"]


def test_commands_render_api_returns_result(project):
    res = commands.render("cube", overrides=["size=2"], skip=["stl"])
    assert res.run_name == "cube" and "glb" in res.written and "stl" not in res.written
    assert res.path_for("glb").exists()


def test_no_command_prints_help(capsys):
    assert main([]) == 2


def test_dotlist_after_flags_is_accepted(project, capsys):
    from bevel_cad.cli.main import hoist_dotlist

    assert hoist_dotlist(["render", "cube", "--skip", "glb", "size=2", "--json"]) == ["render", "cube", "size=2", "--skip", "glb", "--json"]
    assert hoist_dotlist(["render", "--viewer", "cube", "a.b=1"]) == ["render", "cube", "a.b=1", "--viewer"]
    assert hoist_dotlist(["upload", "renders/x", "--name", "n", "viewer.port=1"]) == ["upload", "renders/x", "viewer.port=1", "--name", "n"]
    assert hoist_dotlist(["list", "--json"]) == ["list", "--json"]
    rc = main(["render", "cube", "--skip", "glb,preview", "size=2", "--json"])
    assert rc == 0
    d = _json_out(capsys)
    assert yaml.safe_load((Path(d["bundle_dir"]) / f"{d['stem']}.yaml").read_text())["size"] == 2
