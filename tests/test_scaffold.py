"""bevel create / add / templates / skills."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bevel_cad import scaffold
from bevel_cad.cli import main


def _json(capsys):
    return json.loads(capsys.readouterr().out)


def test_templates_listed(capsys):
    assert main(["templates", "--json"]) == 0
    names = {t["name"]: t for t in _json(capsys)}
    assert set(names) >= {"basic", "label"}
    assert names["label"]["prompts"][0]["key"] == "text"


def test_create_basic_and_render(tmp_path, monkeypatch, clean_logging, capsys):
    monkeypatch.chdir(tmp_path)
    rc = main(["create", "My Block", "--description", "demo", "--format", "step", "--template", "basic", "--yes", "--json"])
    assert rc == 0
    res = _json(capsys)
    root = Path(res["root"])
    assert root == (tmp_path / "My Block").resolve() and res["part_name"] == "my_block"
    assert (root / "bevel.yaml").is_file() and (root / "src" / "my_block.py").is_file()
    assert (root / "configs" / "my_block.yaml").is_file() and (root / "renders" / ".gitkeep").is_file()
    assert (root / ".claude" / "skills").is_dir()
    text = (root / "bevel.yaml").read_text()
    assert "step: {enabled: true}" in text and "stl: {enabled: false}" in text

    monkeypatch.chdir(root)
    assert main(["render", "my_block", "--skip", "preview", "--json"]) == 0
    d = _json(capsys)
    assert set(d["files"]) == {"step", "glb", "config", "stats"}
    assert Path(d["bundle_dir"]).parent == root / "renders"
    # the pocket removed volume from the cube
    from bevel_cad.mesh.inspect import inspect_mesh_file
    import trimesh

    rep = inspect_mesh_file(d["files"]["glb"])
    assert rep.watertight and rep.volume == pytest.approx(50**3 - 3.14159 * 12.5**2 * 25, rel=2e-2)

    # refuses to clobber
    monkeypatch.chdir(tmp_path)
    assert main(["create", "My Block", "--yes"]) == 1
    assert "already exists" in capsys.readouterr().err


def test_add_label_part_and_render(tmp_path, monkeypatch, clean_logging, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["create", "proj", "--yes", "--no-skills", "--json"]) == 0
    root = Path(_json(capsys)["root"])
    monkeypatch.chdir(root)
    assert main(["add", "sign", "--template", "label", "--param", "text=Hi", "--json"]) == 0
    res = _json(capsys)
    assert res["part_name"] == "sign" and (root / "src" / "sign.py").is_file()
    assert 'text: "Hi"' in (root / "configs" / "sign.yaml").read_text()
    assert main(["render", "sign", "--skip", "preview", "--json"]) == 0
    d = _json(capsys)
    assert sorted(Path(p).name for p in d["extra_files"]) == [f"{d['stem']}_plate.stl", f"{d['stem']}_text_fill.stl"]
    assert main(["add", "sign", "--template", "label", "--param", "text=Hi"]) == 1


def test_interactive_prompts(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    answers = iter(["widget", "a thing", "3mf", "label", "Yo"])
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert main(["create", "--no-skills", "--json"]) == 0
    res = _json(capsys)
    root = Path(res["root"])
    assert root.name == "widget"
    assert '"3mf": {enabled: true}' in (root / "bevel.yaml").read_text()
    assert 'text: "Yo"' in (root / "configs" / "widget.yaml").read_text()


def test_non_interactive_missing_name_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert main(["create"]) == 1
    assert "required" in capsys.readouterr().err


def test_add_outside_project_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["add", "x", "--yes"]) == 1
    assert "Not inside a bevel project" in capsys.readouterr().err


def test_skills_list_and_install(tmp_path, capsys):
    assert main(["skills", "list", "--json"]) == 0
    skills = _json(capsys)
    assert skills, "no skills bundled"
    assert main(["skills", "install", "--to", str(tmp_path / "sk"), "--json"]) == 0
    out = _json(capsys)
    assert all(Path(f).is_file() for f in out["files"])
    assert main(["skills", "install", "--to", str(tmp_path / "sk")]) == 1  # exists, no --force
    assert main(["skills", "install", "--to", str(tmp_path / "sk"), "--force"]) == 0
