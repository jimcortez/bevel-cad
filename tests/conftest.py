from __future__ import annotations

from pathlib import Path

import pytest

from bevel_cad.config import load_layers

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """A struct config with defaults only, rendering into tmp_path/renders."""
    monkeypatch.chdir(tmp_path)
    return load_layers(project_config=None, user_config=False, dotlist=["rendering.exports.preview.enabled=false"]).cfg


@pytest.fixture
def clean_logging():
    import logging

    import bevel_cad.render.logbuffer as lb

    old_handlers = logging.root.handlers[:]
    old_level = logging.root.level
    for h in logging.root.handlers[:]:
        logging.root.removeHandler(h)
    lb._memory_handler = None
    lb._saved_root_level = None
    yield
    for h in logging.root.handlers[:]:
        logging.root.removeHandler(h)
        h.close()
    for h in old_handlers:
        logging.root.addHandler(h)
    logging.root.setLevel(old_level)
    lb._memory_handler = None
    lb._saved_root_level = None
