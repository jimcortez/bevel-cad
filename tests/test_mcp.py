"""MCP server exercised through the SDK's in-memory client."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import anyio
import pytest
from mcp.client import Client

from bevel_cad.mcp import create_server

pytestmark = pytest.mark.usefixtures("clean_logging")


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "bevel.yaml").write_text("project:\n  name: mcpdemo\nrendering:\n  exports:\n    preview: {enabled: false}\n")
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "cube.yaml").write_text("part: cube\nsize: 3\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "cube.py").write_text(
        "import bevel_cad\nfrom cadquery.func import box\n\n"
        "@bevel_cad.part(defaults={'size': 2}, description='A cube')\n"
        "def build(cfg):\n    s = float(cfg.size)\n    return box(s, s, s)\n"
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _structured(result):
    if result.structured_content is not None:
        sc = result.structured_content
        return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
    return json.loads(result.content[0].text)


def _run(coro_fn):
    return anyio.run(coro_fn)


def test_tools_listed_with_schemas(project):
    async def go():
        async with Client(create_server(root=project)) as client:
            tools = await client.list_tools()
            names = {t.name: t for t in tools.tools}
            assert {"render", "list_parts", "inspect_mesh", "get_preview", "resolve_config", "create_project"} <= set(names)
            assert "target" in names["render"].input_schema["properties"]
            assert names["render"].input_schema["required"] == ["target"]
            assert "skip" in names["render"].description
            prompts = await client.list_prompts()
            assert {p.name for p in prompts.prompts} == {"build_part", "verify_render", "iterate_model"}
    _run(go)


def test_list_describe_resolve(project):
    async def go():
        async with Client(create_server(root=project)) as client:
            parts = _structured(await client.call_tool("list_parts", {}))
            assert any(p["name"] == "cube" and p["kind"] == "project" for p in parts)
            info = _structured(await client.call_tool("describe_part", {"name": "cube"}))
            assert info["description"] == "A cube" and info["defaults"] == {"size": 2}
            src = await client.call_tool("read_part_source", {"name": "cube"})
            assert "def build(cfg)" in src.content[0].text
            yml = await client.call_tool("resolve_config", {"target": "cube", "overrides": {"size": 9}})
            assert "size: 9" in yml.content[0].text
            pi = _structured(await client.call_tool("project_info", {}))
            assert pi["root"] == str(project.resolve())
    _run(go)


def test_render_inspect_show_in_process(project):
    async def go():
        async with Client(create_server(root=project, in_process_render=True)) as client:
            res = _structured(await client.call_tool("render", {"target": "cube", "skip": ["glb"], "name": "mcp-cube"}))
            assert res["run_name"] == "mcp-cube" and set(res["files"]) == {"stl", "config", "stats"}
            rep = _structured(await client.call_tool("inspect_mesh", {"path": res["files"]["stl"]}))
            assert rep["watertight"] is True and rep["volume"] == pytest.approx(27.0, rel=1e-3)
            listed = _structured(await client.call_tool("list_renders", {}))
            assert listed[0]["stem"] == res["stem"]
            shown = _structured(await client.call_tool("describe_render", {"bundle": res["stem"]}))
            assert shown["config"]["size"] == 3 and "render.run_name" in shown["stats"]
            cfg = await client.read_resource(f"bevel://renders/{res['stem']}/config")
            assert "size: 3" in cfg.contents[0].text
            bad = await client.call_tool("get_preview", {"bundle": res["stem"]})
            assert bad.is_error and "No preview PNG" in bad.content[0].text
    _run(go)


def test_render_subprocess_streams_progress(project):
    async def go():
        seen = []

        async def on_progress(progress, total, message):
            seen.append(message)

        async with Client(create_server(root=project)) as client:
            result = await client.call_tool(
                "render", {"target": "cube", "skip": ["glb", "stats"], "overrides": {"size": 4}}, progress_callback=on_progress
            )
            assert not result.is_error, result.content[0].text
            res = _structured(result)
            assert set(res["files"]) == {"stl", "config"}
            assert Path(res["files"]["stl"]).is_file()
            assert any("STL" in m for m in seen), seen
            failed = await client.call_tool("render", {"target": "nope"})
            assert failed.is_error and "Unknown part target" in failed.content[0].text
    _run(go)


def test_get_preview_returns_image(project, tmp_path):
    bdir = project / "renders" / "x_20250101-120000"
    bdir.mkdir(parents=True)
    png = bytes.fromhex("89504e470d0a1a0a") + b"rest"
    (bdir / "x_20250101-120000.png").write_bytes(png)
    (bdir / "x_20250101-120000.yaml").write_text("rendering: {name: x}\n")

    async def go():
        async with Client(create_server(root=project)) as client:
            r = await client.call_tool("get_preview", {"bundle": "x_20250101-120000"})
            assert r.content[0].type == "image"
            assert base64.b64decode(r.content[0].data) == png
    _run(go)


def test_scaffold_and_skills_tools(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    async def go():
        async with Client(create_server()) as client:
            t = _structured(await client.call_tool("list_templates", {}))
            assert {x["name"] for x in t} >= {"basic", "label"}
            res = _structured(await client.call_tool(
                "create_project", {"name": "viamcp", "template": "label", "params": {"text": "Hi"}, "with_skills": False}
            ))
            root = Path(res["root"])
            assert (root / "src" / "viamcp.py").is_file()
            added = _structured(await client.call_tool("add_part", {"name": "more", "root": str(root)}))
            assert (root / "configs" / "more.yaml").is_file() and added["part_name"] == "more"
            skills = _structured(await client.call_tool("list_skills", {}))
            assert any(s["name"] == "bevel-mcp-workflow" for s in skills)
            txt = await client.call_tool("read_skill", {"name": "bevel-render-verify"})
            assert "bevel inspect" in txt.content[0].text
            prompt = await client.get_prompt("build_part")
            assert "build(cfg)" in prompt.messages[0].content.text
    _run(go)


def test_stdio_server_process(project):
    """`bevel mcp` as a real subprocess over stdio."""
    import sys

    from mcp.client.stdio import StdioServerParameters

    params = StdioServerParameters(command=sys.executable, args=["-m", "bevel_cad", "mcp", "--root", str(project)])

    async def go():
        async with Client(params) as client:
            tools = await client.list_tools()
            assert any(t.name == "render" for t in tools.tools)
            parts = _structured(await client.call_tool("list_parts", {}))
            assert any(p["name"] == "cube" for p in parts)
    _run(go)
