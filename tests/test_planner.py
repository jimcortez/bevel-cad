"""Export job planning from the exports mapping."""

from __future__ import annotations

from pathlib import Path

import pytest
from omegaconf import OmegaConf

from bevel_cad.config import load_layers
from bevel_cad.config.schema import PreviewSettings
from bevel_cad.render.planner import (
    DuplicateExportFilenameError,
    RenderPlanner,
    first_preview_settings,
    job_specs_from_config,
)


def _plan(cfg, **kw):
    return RenderPlanner.plan(cfg, bundle_dir=Path("/tmp/renders/k_20250101-120000"), bundle_stem="k_20250101-120000", run_name="K", **kw)


def test_defaults_enabled_and_order():
    cfg = load_layers(project_config=None, user_config=False).cfg
    specs = {s.name: s for s in job_specs_from_config(cfg)}
    assert specs["stl"].enabled and specs["stats"].enabled and specs["preview"].enabled
    assert not specs["obj"].enabled and not specs["step"].enabled
    plan = _plan(cfg)
    assert [j.format for j in plan.execution_order] == ["stl", "glb", "preview", "config", "stats"]
    assert plan.execution_order[0].resolved_path.name == "k_20250101-120000.stl"
    assert plan.want_viewer is False
    assert _plan(cfg, viewer=True).want_viewer is True


def test_dependency_job_synthesised_when_glb_disabled():
    cfg = load_layers(project_config=None, user_config=False, dotlist=["rendering.exports.glb.enabled=false"]).cfg
    plan = _plan(cfg)
    glb = plan.job("glb")
    assert glb is not None and glb.is_dependency_only and glb.dependency_of == "preview"


def test_no_dependency_when_preview_disabled_too():
    cfg = load_layers(
        project_config=None, user_config=False,
        dotlist=["rendering.exports.glb.enabled=false", "rendering.exports.preview.enabled=false"],
    ).cfg
    assert _plan(cfg).job("glb") is None


def test_extra_preview_job_and_typed_settings():
    cfg = load_layers(
        project_config=None, user_config=False,
        overrides={"rendering": {"exports": {"iso": {"format": "preview", "filename": "{name}-iso.png", "azimuth": 135}}}},
    ).cfg
    plan = _plan(cfg)
    iso = plan.job("iso")
    assert iso is not None and iso.resolved_path.name == "k_20250101-120000-iso.png"
    assert isinstance(iso.typed, PreviewSettings) and iso.typed.azimuth == 135 and iso.typed.elevation == 30
    assert iso.typed.color_rgb == pytest.approx((0.702, 0.702, 0.702), abs=1e-3)
    assert first_preview_settings(cfg).azimuth == 45


def test_duplicate_filename_raises():
    cfg = OmegaConf.create({
        "rendering": {"exports": {"stl": {"enabled": True}, "3mf": {"enabled": True, "filename": "{name}.stl"}}},
        "viewer": {"enabled": False},
    })
    with pytest.raises(DuplicateExportFilenameError):
        _plan(cfg)


def test_unknown_format_and_bad_settings():
    with pytest.raises(ValueError, match="format must be one of"):
        job_specs_from_config(OmegaConf.create({"rendering": {"exports": {"weird": {"format": "dxf"}}}}))
    cfg = OmegaConf.create({"rendering": {"exports": {"preview": {"azimuth": "east"}}}, "viewer": {"enabled": False}})
    with pytest.raises(ValueError, match="invalid settings"):
        _plan(cfg)


def test_filename_template_cannot_escape_bundle():
    cfg = OmegaConf.create({"rendering": {"exports": {"stl": {"filename": "../{name}.stl"}}}, "viewer": {"enabled": False}})
    with pytest.raises(ValueError, match="Invalid export filename"):
        _plan(cfg)
