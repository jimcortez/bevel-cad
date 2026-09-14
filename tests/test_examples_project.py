"""The examples/ folder is a self-contained bevel project."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from bevel_cad.cli import main
from tests.conftest import EXAMPLES, load_example


def _json(capsys):
    return json.loads(capsys.readouterr().out)


def test_examples_layout():
    assert (EXAMPLES / "bevel.yaml").is_file()
    assert (EXAMPLES / "renders" / ".gitkeep").is_file()
    assert {p.stem for p in (EXAMPLES / "src").glob("*.py")} == {"button_label", "spacer_washer"}
    assert {p.stem for p in (EXAMPLES / "configs").glob("*.yaml")} == {"button_label", "button_label_custom", "spacer_washer"}


def test_spacer_washer_geometry():
    sw = load_example("spacer_washer")
    solid = sw.build_spacer_washer(outer_diameter_in=1.0, height_in=0.25, hole_diameter_in=0.25, fillet_mm=0)
    import math

    expected = math.pi * ((12.7**2) - (3.175**2)) * 6.35
    assert solid.Volume() == pytest.approx(expected, rel=1e-3)
    with pytest.raises(ValueError):
        sw.build_spacer_washer(hole_diameter_in=2.0)


def test_examples_project_renders_from_a_copy(tmp_path, monkeypatch, clean_logging, capsys):
    """Copy examples/ elsewhere: it must work with no reference to the repo."""
    proj = tmp_path / "copied_examples"
    shutil.copytree(EXAMPLES, proj, ignore=shutil.ignore_patterns("renders", "__pycache__"))
    monkeypatch.chdir(proj)
    assert main(["list", "--json"]) == 0
    names = {p["name"]: p["kind"] for p in _json(capsys)}
    assert names["button_label"] == "project" and names["spacer_washer"] == "project"

    assert main(["render", "spacer_washer", "--skip", "preview", "spacer_washer.hole_diameter_in=0.3", "--json"]) == 0
    d = _json(capsys)
    assert Path(d["bundle_dir"]).parent == proj / "renders" and "stl" in d["files"]

    assert main(["render", "button_label_custom", "--skip", "preview", "--json"]) == 0
    d = _json(capsys)
    assert d["run_name"] == "custom_label"
    assert sorted(Path(p).name for p in d["extra_files"]) == [f"{d['stem']}_plate.stl", f"{d['stem']}_text_fill.stl"]
