"""Tests for render stats collection and CSV output."""

from __future__ import annotations

import logging
from pathlib import Path

from bevel_cad.render.stats import RenderStats, describe_stage, read_stats_csv, register_stage_descriptions


def test_describe_stage_registered_stages():
    register_stage_descriptions({"custom.sweep": "Sweeping tube along path"})
    assert describe_stage("custom.sweep") == "Sweeping tube along path"
    assert describe_stage("unknown.stage") == "unknown.stage"


def test_describe_stage_export_job():
    assert describe_stage("render.job.stl.part.stl") == "Exporting STL (part.stl)"
    assert describe_stage("render.job.preview.part.png") == "Rendering preview (part.png)"
    assert describe_stage("render.job.config.part.yaml") == "Writing config snapshot (part.yaml)"


def test_record_stage_logs_start_and_end(caplog):
    register_stage_descriptions({"custom.sweep": "Sweeping tube along path"})
    caplog.set_level(logging.INFO, logger="bevel_cad.render.stats")
    stats = RenderStats()
    with stats.record_stage("custom.sweep"):
        pass
    messages = [record.message for record in caplog.records]
    assert messages[0] == "Sweeping tube along path"
    assert messages[1].startswith("Sweeping tube along path completed (")
    assert messages[1].endswith("s)")


def test_add_stat_namespacing():
    stats = RenderStats()
    stats.add_stat("draw_part.sweep.duration_s", 1.25, "Sweep stage duration")
    assert len(stats.stats) == 1
    assert stats.stats[0].name == "draw_part.sweep.duration_s"
    assert stats.get("draw_part.sweep.duration_s") == "1.25"
    assert stats.get("missing") is None


def test_write_csv_column_alignment_and_roundtrip(tmp_path: Path):
    stats = RenderStats()
    stats.add_stat("a", "x", "short")
    stats.add_stat("longer.name", "value", "much longer description field")
    out = tmp_path / "stats.csv"
    stats.write_csv(out)
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("name")
    widths = [len(part) for part in lines[1].split(", ")]
    widths2 = [len(part) for part in lines[2].split(", ")]
    assert widths[0] == widths2[0]
    assert widths[1] == widths2[1]
    parsed = read_stats_csv(out)
    assert [(s.name, s.value) for s in parsed] == [("a", "x"), ("longer.name", "value")]


def test_git_and_config_sources_populated(tmp_path: Path):
    stats = RenderStats()
    stats.populate_config_sources([("defaults", None), ("project", tmp_path / "bevel.yaml")])
    stats.populate_git_info()
    names = {s.name for s in stats.stats}
    assert "config.sources.0.defaults" in names
    assert "config.sources.1.project" in names
    assert stats.get("config.sources.1.project") == str(tmp_path / "bevel.yaml")
    assert "git.branch" in names
    assert "git.commit" in names
