"""End-to-end render_part behaviour on tiny geometry."""

from __future__ import annotations

import logging
import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import cadquery as cq
import pytest
import trimesh
import yaml
from cadquery.func import box

from bevel_cad.config import load_layers
from bevel_cad.render.pipeline import ExportError, PartArtifacts, render_part, start_run


def _cfg(tmp_path, monkeypatch, *dotlist, **kw):
    monkeypatch.chdir(tmp_path)
    return load_layers(project_config=None, user_config=False, dotlist=list(dotlist), **kw).cfg


def test_render_solid_writes_bundle(tmp_path, monkeypatch, clean_logging):
    cfg = _cfg(tmp_path, monkeypatch, "rendering.exports.preview.enabled=false", "rendering.exports.step.enabled=true",
               "rendering.exports.3mf.enabled=true", "rendering.exports.obj.enabled=true", "rendering.exports.gltf.enabled=true")
    run = start_run(cfg, name="My Box", now=datetime(2025, 1, 1, 12, 0, 0), part_source="file:box.py")
    assert run.stem == "my-box_20250101-120000"
    assert run.bundle_dir == (tmp_path / "renders" / run.stem).resolve()

    res = render_part(box(10, 10, 10), run)
    names = sorted(p.name for p in res.bundle_dir.iterdir())
    assert names == sorted(f"{run.stem}{ext}" for ext in (".stl", ".step", ".3mf", ".glb", ".gltf", ".obj", ".yaml", ".csv", ".log"))
    assert set(res.written) == {"stl", "step", "3mf", "glb", "gltf", "obj", "config", "stats"}
    assert res.path_for("stl") == res.bundle_dir / f"{run.stem}.stl"
    # 3MF is a real zip container, not renamed STL bytes.
    assert zipfile.is_zipfile(res.path_for("3mf"))
    # binary STL (stl_ascii defaults to false) and a watertight mesh
    stl = res.path_for("stl").read_bytes()
    assert not stl.startswith(b"solid ")
    assert trimesh.load(res.path_for("stl")).is_watertight
    # config snapshot is re-loadable and pins the run name + part
    snap = yaml.safe_load(res.path_for("config").read_text())
    assert snap["rendering"]["name"] == "My Box"
    assert snap["part"] == "file:box.py"
    assert snap["rendering"]["exports"]["stl"]["enabled"] is True
    # stats + log
    csv = res.path_for("stats").read_text()
    assert "render.run_name" in csv and "render.job.stl" in csv
    assert (res.bundle_dir / f"{run.stem}.log").exists()
    d = res.to_dict()
    assert d["run_name"] == "My Box" and d["files"]["glb"].endswith(".glb")


def test_assembly_body_stls_and_workplane_and_wrapped(tmp_path, monkeypatch, clean_logging):
    cfg = _cfg(tmp_path, monkeypatch, "rendering.exports.preview.enabled=false")
    assy = cq.Assembly(name="Two Boxes")
    assy = assy.add(box(10, 10, 4), name="plate")
    assy = assy.add(box(2, 2, 1).moved(cq.Location((0, 0, 3))), name="text fill")
    res = render_part(assy, cfg, name="two")
    assert [p.name for p in res.extra_paths] == [f"{res.stem}_plate.stl", f"{res.stem}_text-fill.stl"]
    assert all(p.stat().st_size > 0 for p in res.extra_paths)

    run = start_run(cfg, name="wp")
    ctx = PartArtifacts(cq.Workplane("XY").box(1, 1, 1), run)
    assert isinstance(ctx.solid, cq.Shape) and not ctx.is_assembly

    class Wrapped:  # build123d-style duck type
        def __init__(self, shape):
            self.wrapped = shape.wrapped

    ctx2 = PartArtifacts(Wrapped(box(1, 1, 1)), run)
    assert ctx2.solid.Volume() == pytest.approx(1.0)
    with pytest.raises(TypeError):
        PartArtifacts(object(), run)._normalize()


def test_mesh_input_exports_stl_but_rejects_step(tmp_path, monkeypatch, clean_logging):
    cfg = _cfg(tmp_path, monkeypatch, "rendering.exports.preview.enabled=false")
    mesh = trimesh.creation.box(extents=(1, 1, 1))
    res = render_part(mesh, cfg, name="mesh")
    assert res.path_for("stl").exists() and res.path_for("glb").exists()
    cfg2 = _cfg(tmp_path, monkeypatch, "rendering.exports.preview.enabled=false", "rendering.exports.step.enabled=true")
    with pytest.raises(ExportError, match="STEP export requires a B-rep"):
        render_part(mesh, cfg2, name="mesh2")


def test_no_side_effects_creates_nothing(tmp_path, monkeypatch, clean_logging):
    dots = [f"rendering.exports.{f}.enabled=false" for f in ("stl", "preview", "glb", "config", "stats")]
    cfg = _cfg(tmp_path, monkeypatch, *dots)
    res = render_part(box(1, 1, 1), cfg, name="nothing")
    assert res.written == {} and not (tmp_path / "renders").exists()
    assert res.to_dict()["bundle_dir"] is None


def test_viewer_pushed_after_files(tmp_path, monkeypatch, clean_logging):
    cfg = _cfg(tmp_path, monkeypatch, "rendering.exports.preview.enabled=false")
    order = []
    orig_exec = PartArtifacts.execute_job

    def exec_spy(self, job):
        order.append(("file", job.format))
        return orig_exec(self, job)

    with patch.object(PartArtifacts, "execute_job", exec_spy), \
         patch("bevel_cad.viewer.ensure_reachable") as reach, \
         patch("bevel_cad.viewer._show") as show:
        res = render_part(box(1, 1, 1), cfg, name="Viewed", viewer=True)
    reach.assert_called_once()
    assert order[0][0] == "file" and show.call_count == 1
    assert res.viewer_names == ("Viewed",)
    # single body -> bundle GLB bytes were uploaded
    assert show.call_args[0][0] == res.path_for("glb").read_bytes()
    assert show.call_args[1]["names"] == "Viewed" and show.call_args[1]["server_type"] == "remote"


def test_viewer_colored_parts_for_assembly(tmp_path, monkeypatch, clean_logging):
    cfg = _cfg(tmp_path, monkeypatch, "rendering.exports.preview.enabled=false")
    assy = cq.Assembly(name="A").add(box(1, 1, 1), name="a").add(box(1, 1, 1).moved(cq.Location((3, 0, 0))), name="b")
    with patch("bevel_cad.viewer.ensure_reachable"), patch("bevel_cad.viewer._show") as show:
        res = render_part(assy, cfg, name="pair", viewer=True)
    assert res.viewer_names == ("a", "b") and show.call_count == 2
    assert show.call_args_list[0][1]["auto_clear"] is True and show.call_args_list[1][1]["auto_clear"] is False
    assert show.call_args_list[0][1]["color_faces"] is not None


def test_viewer_unreachable_raises_before_writing(tmp_path, monkeypatch, clean_logging):
    from bevel_cad.viewer import ViewerUnreachable

    cfg = _cfg(tmp_path, monkeypatch, "rendering.exports.preview.enabled=false", "viewer.port=1")
    with pytest.raises(ViewerUnreachable, match="cadquery-web-viewer --host localhost --port 1"):
        render_part(box(1, 1, 1), cfg, name="v", viewer=True)
    assert not (tmp_path / "renders").exists()


def test_preview_png_rendered(tmp_path, monkeypatch, clean_logging):
    cfg = _cfg(tmp_path, monkeypatch, "rendering.exports.stats.enabled=false", "rendering.exports.config.enabled=false")
    try:
        res = render_part(box(5, 5, 5), cfg, name="pv")
    except Exception as exc:  # no GL context on this machine
        pytest.skip(f"offscreen rendering unavailable: {exc!r}")
    png = res.path_for("preview")
    assert png is not None and png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
