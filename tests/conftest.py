from __future__ import annotations

import os
import sys
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

EXAMPLES = Path(__file__).parent.parent / "examples"


def load_example(name: str):
    """Import ``examples/src/<name>.py`` as a module (the examples are a standalone project)."""
    from bevel_cad.parts import load_module_from_file

    return load_module_from_file(EXAMPLES / "src" / f"{name}.py")


# --- Windows: leave the interpreter without running OCP/VTK static destructors ---------
# On Windows those destructors can raise an access violation (0xC0000005) during interpreter
# teardown, *after* pytest has printed its summary, turning a green run into a failed step.
# The CLI does the same in bevel_cad.cli.run(). No-op on other platforms.

_EXIT_STATUS = 0


def pytest_sessionfinish(session, exitstatus):
    global _EXIT_STATUS
    _EXIT_STATUS = int(exitstatus)


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    if sys.platform == "win32":
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(_EXIT_STATUS)
