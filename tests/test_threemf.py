"""3MF export: one welded, closed mesh object per body, written by trimesh."""

from __future__ import annotations

import zipfile

import cadquery as cq
import numpy as np
import pytest
import trimesh
from cadquery.func import box

from bevel_cad.config import load_layers
from bevel_cad.mesh.threemf import ThreeMfError, open_edge_count, weld_body, write_3mf
from bevel_cad.render.pipeline import render_part


def _cfg(tmp_path, monkeypatch, *dotlist):
    monkeypatch.chdir(tmp_path)
    dots = ["rendering.exports.preview.enabled=false", "rendering.exports.3mf.enabled=true", *dotlist]
    return load_layers(project_config=None, user_config=False, dotlist=dots).cfg


def _read_3mf(path) -> trimesh.Scene:
    """The 3MF exactly as written: ``process=False`` keeps the file's own vertex indexing."""
    with zipfile.ZipFile(path) as zf:
        assert {"[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model"} <= set(zf.namelist())
        assert b'unit="millimeter"' in zf.read("3D/3dmodel.model")
    return trimesh.load(str(path), file_type="3mf", process=False)


def _polyhedron_solid(mesh: trimesh.Trimesh) -> cq.Solid:
    """A B-rep solid whose every face is one triangle (like a mesh sewn into OCC)."""
    faces = [
        cq.Face.makeFromWires(cq.Wire.makePolygon([cq.Vector(*mesh.vertices[i]) for i in tri], close=True))
        for tri in mesh.faces
    ]
    solid = cq.Solid.makeSolid(cq.Shell.makeShell(faces))
    assert solid.isValid()
    return solid


# --- helpers -------------------------------------------------------------------------------------
def test_weld_merges_triangle_soup_into_a_closed_mesh():
    cube = trimesh.creation.box()
    soup = trimesh.Trimesh(cube.triangles.reshape(-1, 3), np.arange(36).reshape(-1, 3), process=False)
    assert open_edge_count(soup) == 36  # every edge open, as CadQuery's exporter writes it
    welded = weld_body("cube", soup, require_closed=True)
    assert len(welded.vertices) == 8 and len(welded.faces) == 12
    assert welded.is_watertight and open_edge_count(welded) == 0
    assert len(soup.vertices) == 36  # the input is not modified


def test_weld_rejects_open_mesh_from_closed_solid_and_degenerate_triangles():
    cube = trimesh.creation.box()
    open_mesh = trimesh.Trimesh(cube.vertices, cube.faces[1:], process=False)
    with pytest.raises(ThreeMfError, match="3 open edges"):
        weld_body("open", open_mesh, require_closed=True)
    assert len(weld_body("open", open_mesh, require_closed=False).faces) == 11
    degenerate = trimesh.Trimesh([[0, 0, 0], [1, 0, 0], [0, 0, 0]], [[0, 1, 2]], process=False)
    with pytest.raises(ThreeMfError, match="repeat a vertex"):
        weld_body("flat", degenerate, require_closed=False)


def test_write_rejects_duplicate_names_and_empty_input(tmp_path):
    body = weld_body("a", trimesh.creation.box(), require_closed=True)
    with pytest.raises(ThreeMfError, match="unique"):
        write_3mf(tmp_path / "x.3mf", [("a", body), ("a", body)])
    with pytest.raises(ThreeMfError, match="no bodies"):
        write_3mf(tmp_path / "x.3mf", [])


# --- pipeline ------------------------------------------------------------------------------------
def test_assembly_3mf_has_one_closed_object_per_body(tmp_path, monkeypatch, clean_logging):
    cfg = _cfg(tmp_path, monkeypatch)
    ico = trimesh.creation.icosphere(subdivisions=2, radius=5.0)
    assy = (
        cq.Assembly(name="pair")
        .add(box(10, 10, 4), name="plate")
        .add(_polyhedron_solid(ico).moved(cq.Location((20, 0, 0))), name="ball")
    )
    res = render_part(assy, cfg, name="pair")
    scene = _read_3mf(res.path_for("3mf"))
    assert sorted(scene.geometry) == ["ball", "plate"]
    for name, mesh in scene.geometry.items():
        assert mesh.is_watertight, f"{name}: {open_edge_count(mesh)} open edges in the file"
        assert len(mesh.vertices) < len(mesh.faces)  # vertices are shared, not three per triangle
    ball = scene.geometry["ball"]
    assert len(ball.faces) == len(ico.faces) and len(ball.vertices) == len(ico.vertices)  # every face a triangle, all welded
    assert ball.volume == pytest.approx(ico.volume, rel=1e-6)
    assert ball.vertices[:, 0].mean() == pytest.approx(20.0, abs=1e-6)  # world placement kept
    assert scene.geometry["plate"].volume == pytest.approx(400.0, rel=1e-6)


def test_single_solid_3mf_is_one_object_named_after_the_run(tmp_path, monkeypatch, clean_logging):
    cfg = _cfg(tmp_path, monkeypatch)
    res = render_part(cq.Workplane("XY").cylinder(10, 4).val(), cfg, name="Rod")
    scene = _read_3mf(res.path_for("3mf"))
    assert list(scene.geometry) == ["Rod"]
    rod = scene.geometry["Rod"]
    assert rod.is_watertight
    assert rod.volume == pytest.approx(np.pi * 16 * 10, rel=0.01)
