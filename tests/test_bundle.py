"""Tests for render bundle resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from bevel_cad.render.bundle import resolve_render_bundle


def write_bundle(tmp_path: Path, stem: str = "rod_20260612-152817", *, with_yaml=True, with_glb=True, yaml_body=None) -> Path:
    bundle_dir = tmp_path / stem
    bundle_dir.mkdir(parents=True)
    if with_glb:
        (bundle_dir / f"{stem}.glb").write_bytes(b"glb-bytes")
    if with_yaml:
        (bundle_dir / f"{stem}.yaml").write_text(
            yaml_body or "rendering:\n  name: rod\nviewer:\n  host: testhost\n  port: 42424\n",
            encoding="utf-8",
        )
    return bundle_dir


def test_resolve_render_bundle_from_directory(tmp_path):
    bundle_dir = write_bundle(tmp_path)
    bundle = resolve_render_bundle(bundle_dir)
    assert bundle.stem == bundle_dir.name
    assert bundle.glb_path == bundle_dir / f"{bundle_dir.name}.glb"
    assert bundle.config_yaml == bundle_dir / f"{bundle_dir.name}.yaml"


def test_resolve_render_bundle_from_yaml_path(tmp_path):
    bundle_dir = write_bundle(tmp_path)
    bundle = resolve_render_bundle(bundle_dir / f"{bundle_dir.name}.yaml")
    assert bundle.bundle_dir == bundle_dir.resolve()
    assert bundle.glb_path.name == f"{bundle_dir.name}.glb"


def test_resolve_render_bundle_missing_glb_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="GLB not found"):
        resolve_render_bundle(write_bundle(tmp_path, with_glb=False))


def test_resolve_render_bundle_invalid_path_raises(tmp_path):
    with pytest.raises(ValueError, match="directory or YAML"):
        resolve_render_bundle(tmp_path / "missing.txt")
