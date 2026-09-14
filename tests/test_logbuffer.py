"""Tests for per-render log buffering and bundle log files."""

from __future__ import annotations

import io
import logging
import re

import pytest

import bevel_cad.render.logbuffer as render_logging_module
from bevel_cad.render.logbuffer import (
    attach_render_log_buffer,
    discard_render_log_buffer,
    finalize_render_log,
)

TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} ")


@pytest.fixture
def clean_render_logging():
    old_handlers = logging.root.handlers[:]
    old_level = logging.root.level
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
        handler.close()
    render_logging_module._memory_handler = None
    render_logging_module._saved_root_level = None
    yield
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
        handler.close()
    for handler in old_handlers:
        logging.root.addHandler(handler)
    logging.root.setLevel(old_level)
    render_logging_module._memory_handler = None
    render_logging_module._saved_root_level = None


def test_finalize_writes_timestamped_debug_and_info(tmp_path, clean_render_logging):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    attach_render_log_buffer()
    log = logging.getLogger("test.module")
    log.debug("debug line")
    log.info("info line")

    log_path = tmp_path / "run.log"
    finalize_render_log(log_path)

    text = log_path.read_text(encoding="utf-8")
    assert "debug line" in text
    assert "info line" in text
    for line in text.strip().splitlines():
        assert TIMESTAMP_RE.match(line), line


def test_discard_does_not_write_log(tmp_path, clean_render_logging):
    logging.basicConfig(level=logging.INFO)
    attach_render_log_buffer()
    logging.getLogger("test").info("msg")

    log_path = tmp_path / "run.log"
    discard_render_log_buffer()

    assert not log_path.exists()


def test_file_log_includes_debug_while_stderr_is_info(tmp_path, clean_render_logging):
    stream = io.StringIO()
    stream_handler = logging.StreamHandler(stream)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    logging.root.addHandler(stream_handler)
    logging.root.setLevel(logging.INFO)

    attach_render_log_buffer()
    log = logging.getLogger("test")
    log.debug("secret debug")
    log.info("visible info")

    finalize_render_log(tmp_path / "run.log")

    output = stream.getvalue()
    assert "secret debug" not in output
    assert "visible info" in output
    text = (tmp_path / "run.log").read_text(encoding="utf-8")
    assert "secret debug" in text
    assert "visible info" in text
