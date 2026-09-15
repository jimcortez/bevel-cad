"""
MCP server over :mod:`bevel_cad.commands`.

Every tool mirrors a CLI command and returns the same JSON the CLI prints with
``--json``.  ``render`` executes in a subprocess so a crash inside OCC cannot
take the server down; its log lines are streamed back as progress.
"""

from __future__ import annotations

import base64
import json
import logging
import shlex
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server import MCPServer
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ImageContent

from bevel_cad import __version__, commands, scaffold
from bevel_cad.commands import CommandError, Hooks

logger = logging.getLogger(__name__)

INSTRUCTIONS = """bevel renders CadQuery parts into timestamped render bundles.

Reliable sequence: list_parts -> describe_part -> resolve_config -> render (skip=["preview","stats"] while
iterating) -> inspect_mesh on every STL in the result -> get_preview and LOOK at it -> upload to the
viewer only when the geometry is right. Read the `bevel-mcp-workflow` skill (read_skill) for details.
Parts live in <root>/src/<name>.py, per-part config in <root>/configs/<name>.yaml, bundles in <root>/renders/.
"""

_SKILL_PROMPTS = {
    "build_part": "bevel-part-authoring",
    "verify_render": "bevel-render-verify",
    "iterate_model": "bevel-model-iteration",
}


def _root(server_root: Optional[Path], override: Optional[str]) -> Optional[str]:
    if override:
        return override
    return str(server_root) if server_root else None


def _err(exc: Exception) -> Dict[str, Any]:
    return {"error": str(exc), "type": type(exc).__name__}


_USER_ERRORS = (CommandError, scaffold.ScaffoldError, ValueError, FileNotFoundError, LookupError)


def _guard(fn):
    """Turn user-facing failures into ToolError so the message reaches the agent verbatim."""
    import functools
    import inspect as _inspect

    if _inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def aw(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except _USER_ERRORS as exc:
                raise ToolError(str(exc)) from exc

        return aw

    @functools.wraps(fn)
    def w(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except _USER_ERRORS as exc:
            raise ToolError(str(exc)) from exc

    return w


def _skill_text(name: str) -> str:
    for s in scaffold.list_skills():
        if s.name == name:
            return (Path(s.path) / "SKILL.md").read_text(encoding="utf-8")
    raise CommandError(f"Unknown skill {name!r}; available: {', '.join(s.name for s in scaffold.list_skills())}")


async def _run_render_subprocess(
    argv: List[str], *, ctx: Optional[Context], timeout: float, cwd: Optional[str]
) -> Dict[str, Any]:
    """Run ``bevel render --json`` in a child process, forwarding stderr lines as progress."""
    import anyio
    from anyio.streams.text import TextReceiveStream

    cmd = [sys.executable, "-m", "bevel_cad", *argv]
    if ctx is not None:
        await ctx.info(f"$ {shlex.join(cmd)}")
    stdout_chunks: List[str] = []
    stderr_lines: List[str] = []
    progress = 0
    with anyio.fail_after(timeout):
        async with await anyio.open_process(cmd, cwd=cwd) as proc:

            async def pump_stdout() -> None:
                async for chunk in TextReceiveStream(proc.stdout):
                    stdout_chunks.append(chunk)

            async def pump_stderr() -> None:
                nonlocal progress
                buf = ""
                async for chunk in TextReceiveStream(proc.stderr):
                    buf += chunk
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        line = line.rstrip()
                        if not line:
                            continue
                        stderr_lines.append(line)
                        if ctx is not None:
                            try:
                                if " completed (" in line or "Exported " in line or "Wrote render bundle" in line:
                                    progress += 1
                                    await ctx.report_progress(progress, None, line)
                                elif "ERROR" in line or "WARNING" in line:
                                    await ctx.warning(line)
                                else:
                                    await ctx.debug(line)
                            except Exception:  # noqa: BLE001 - progress is best effort
                                pass
                if buf.strip():
                    stderr_lines.append(buf.strip())

            async with anyio.create_task_group() as tg:
                tg.start_soon(pump_stdout)
                tg.start_soon(pump_stderr)
            rc = await proc.wait()
    out = "".join(stdout_chunks).strip()
    if rc != 0:
        err = next((ln for ln in reversed(stderr_lines) if ln.startswith("error:")), None)
        tail = "\n".join(stderr_lines[-15:])
        raise CommandError((err or f"bevel render exited with code {rc}") + ("\n" + tail if tail else ""))
    start = out.find("{")
    if start < 0:
        raise CommandError("bevel render produced no JSON result\n" + "\n".join(stderr_lines[-15:]))
    data = json.loads(out[start:])
    data["log_tail"] = stderr_lines[-25:]
    return data


def create_server(
    *,
    root: Optional[Path] = None,
    hooks: Optional[Hooks] = None,
    render_timeout: float = 1800.0,
    in_process_render: bool = False,
) -> MCPServer:
    """Build the MCPServer. ``in_process_render=True`` runs renders in this process (tests)."""
    server_root = Path(root).resolve() if root else None
    hooks = commands.resolve_hooks(hooks, server_root)
    mcp = MCPServer("bevel", instructions=INSTRUCTIONS, version=__version__)

    # --- project / parts --------------------------------------------------------------------
    @mcp.tool()
    @_guard
    def project_info(root: Optional[str] = None) -> Dict[str, Any]:
        """Detected project root, layout (configs/src/renders dirs), config sources and resolved project config."""
        return commands.project_info(root=_root(server_root, root), hooks=hooks)

    @mcp.tool()
    @_guard
    def list_parts(root: Optional[str] = None) -> List[Dict[str, Any]]:
        """Every renderable part: project src/ files, registered entry points, bundled examples (no import)."""
        return [p.to_dict() for p in commands.list_parts(root=_root(server_root, root), hooks=hooks)]

    @mcp.tool()
    @_guard
    def describe_part(name: str, root: Optional[str] = None) -> Dict[str, Any]:
        """Import one part and return its description, source path and declared config defaults."""
        return commands.describe_part(name, root=_root(server_root, root), hooks=hooks).to_dict()

    @mcp.tool()
    @_guard
    def read_part_source(name: str, root: Optional[str] = None) -> str:
        """The Python source of a part (by name, file path, or module)."""
        return commands.read_part_source(name, root=_root(server_root, root), hooks=hooks)

    @mcp.tool()
    @_guard
    def resolve_config(
        target: Optional[str] = None,
        configs: Optional[List[str]] = None,
        overrides: Optional[Dict[str, Any]] = None,
        root: Optional[str] = None,
    ) -> str:
        """The fully merged YAML config a render of `target` would use (defaults + project + part + configs + overrides)."""
        dots = [f"{k}={json.dumps(v) if not isinstance(v, str) else v}" for k, v in (overrides or {}).items()]
        return commands.resolve_config(target, configs=configs or [], overrides=dots, root=_root(server_root, root), hooks=hooks)

    # --- render -----------------------------------------------------------------------------
    @mcp.tool()
    @_guard
    async def render(
        target: str,
        configs: Optional[List[str]] = None,
        overrides: Optional[Dict[str, Any]] = None,
        name: Optional[str] = None,
        only: Optional[List[str]] = None,
        skip: Optional[List[str]] = None,
        viewer: bool = False,
        out: Optional[str] = None,
        root: Optional[str] = None,
        ctx: Context = None,  # type: ignore[assignment]
    ) -> Dict[str, Any]:
        """Build `target` and write its render bundle. Returns bundle_dir, files{job: path}, extra_files (per-body STLs), stats.

        Use skip=["preview","stats"] for fast iteration; overrides={"block.size": 40} for one-off values;
        viewer=True pushes to cadquery-web-viewer (must already be running)."""
        dots = [f"{k}={json.dumps(v) if not isinstance(v, str) else v}" for k, v in (overrides or {}).items()]
        r = _root(server_root, root)
        if in_process_render:
            res = commands.render(
                target, configs=configs or [], overrides=dots, name=name, out=out, only=only or [], skip=skip or [],
                viewer=viewer if viewer else None, root=r, hooks=hooks,
            )
            return res.to_dict()
        argv = ["render", target, *dots, "--json"]
        for c in configs or []:
            argv += ["-c", c]
        if name:
            argv += ["--name", name]
        if out:
            argv += ["--out", out]
        if only:
            argv += ["--only", ",".join(only)]
        if skip:
            argv += ["--skip", ",".join(skip)]
        if viewer:
            argv.append("--viewer")
        if r:
            argv += ["--root", r]
        return await _run_render_subprocess(argv, ctx=ctx, timeout=render_timeout, cwd=r)

    @mcp.tool()
    @_guard
    def get_preview(bundle: str, view: str = "preview", root: Optional[str] = None) -> ImageContent:
        """The preview PNG of a bundle (dir, stem, or snapshot yaml) as an image. `view` selects an extra preview job by filename suffix."""
        info = commands.describe_render(bundle, root=_root(server_root, root), hooks=hooks)
        bdir = Path(info.bundle_dir)
        candidates = [bdir / f"{info.stem}.png"] if view == "preview" else []
        candidates += sorted(bdir.glob(f"*{view}*.png")) + sorted(bdir.glob("*.png"))
        png = next((p for p in candidates if p.is_file()), None)
        if png is None:
            raise CommandError(f"No preview PNG in {bdir} (render with the preview export enabled)")
        return ImageContent(type="image", mimeType="image/png", data=base64.b64encode(png.read_bytes()).decode("ascii"))

    @mcp.tool()
    @_guard
    def inspect_mesh(path: str) -> Dict[str, Any]:
        """Watertightness, component count, boundary/non-manifold edges, volume and extents of an STL/GLB/OBJ."""
        return commands.inspect_mesh([path])[0].to_dict()

    @mcp.tool()
    @_guard
    def list_renders(limit: int = 20, root: Optional[str] = None) -> List[Dict[str, Any]]:
        """Render bundles in the project's renders dir, newest first."""
        return [b.to_dict() for b in commands.list_renders(root=_root(server_root, root), limit=limit, hooks=hooks)]

    @mcp.tool()
    @_guard
    def describe_render(bundle: str, root: Optional[str] = None) -> Dict[str, Any]:
        """Files, config snapshot, stats and log tail of one bundle (dir, stem, or snapshot yaml)."""
        return commands.describe_render(bundle, root=_root(server_root, root), hooks=hooks).to_dict()

    @mcp.tool()
    @_guard
    def upload(bundle: str, name: Optional[str] = None, root: Optional[str] = None) -> Dict[str, Any]:
        """Push an existing bundle's GLB to the running cadquery-web-viewer."""
        return commands.upload(bundle, name=name, root=_root(server_root, root)).to_dict()

    # --- scaffolding ------------------------------------------------------------------------
    @mcp.tool()
    @_guard
    def list_templates() -> List[Dict[str, Any]]:
        """Starting templates for create_project / add_part and the parameters they ask for."""
        return [t.to_dict() for t in scaffold.list_templates()]

    @mcp.tool()
    @_guard
    def create_project(
        name: str,
        description: str = "",
        format: str = "stl",
        template: str = "basic",
        directory: Optional[str] = None,
        params: Optional[Dict[str, str]] = None,
        with_skills: bool = True,
    ) -> Dict[str, Any]:
        """Scaffold a new bevel project (bevel.yaml, configs/, src/, renders/) with a first part from `template`."""
        try:
            return scaffold.create_project(
                name, description=description, format=format, template=template,
                directory=Path(directory) if directory else None, params=params, with_skills=with_skills,
            ).to_dict()
        except scaffold.ScaffoldError as exc:
            raise CommandError(str(exc)) from exc

    @mcp.tool()
    @_guard
    def add_part(
        name: str, template: str = "basic", description: str = "", params: Optional[Dict[str, str]] = None,
        root: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add src/<name>.py + configs/<name>.yaml to the project from a template."""
        r = _root(server_root, root)
        try:
            return scaffold.add_part(name, template=template, description=description, root=Path(r) if r else None, params=params).to_dict()
        except scaffold.ScaffoldError as exc:
            raise CommandError(str(exc)) from exc

    @mcp.tool()
    @_guard
    def list_skills() -> List[Dict[str, Any]]:
        """Bundled agent skills (how to build, verify, iterate, and use this server)."""
        return [s.to_dict() for s in scaffold.list_skills()]

    @mcp.tool()
    @_guard
    def read_skill(name: str) -> str:
        """Full text of one bundled skill (e.g. bevel-part-authoring)."""
        return _skill_text(name)

    # --- resources --------------------------------------------------------------------------
    @mcp.resource("bevel://project", mime_type="application/json")
    def project_resource() -> str:
        return json.dumps(commands.project_info(root=_root(server_root, None), hooks=hooks), default=str)

    @mcp.resource("bevel://parts/{name}", mime_type="application/json")
    def part_resource(name: str) -> str:
        info = commands.describe_part(name, root=_root(server_root, None), hooks=hooks).to_dict()
        if info.get("path"):
            info["source"] = Path(info["path"]).read_text(encoding="utf-8")
        return json.dumps(info, default=str)

    @mcp.resource("bevel://renders/{stem}/config", mime_type="application/x-yaml")
    def render_config_resource(stem: str) -> str:
        info = commands.describe_render(stem, root=_root(server_root, None), hooks=hooks)
        return (Path(info.bundle_dir) / f"{info.stem}.yaml").read_text(encoding="utf-8")

    @mcp.resource("bevel://renders/{stem}/stats", mime_type="text/csv")
    def render_stats_resource(stem: str) -> str:
        info = commands.describe_render(stem, root=_root(server_root, None), hooks=hooks)
        return (Path(info.bundle_dir) / f"{info.stem}.csv").read_text(encoding="utf-8")

    @mcp.resource("bevel://renders/{stem}/log", mime_type="text/plain")
    def render_log_resource(stem: str) -> str:
        info = commands.describe_render(stem, root=_root(server_root, None), hooks=hooks)
        return (Path(info.bundle_dir) / f"{info.stem}.log").read_text(encoding="utf-8", errors="replace")

    @mcp.resource("bevel://skills/{name}", mime_type="text/markdown")
    def skill_resource(name: str) -> str:
        return _skill_text(name)

    # --- prompts ----------------------------------------------------------------------------
    for prompt_name, skill_name in _SKILL_PROMPTS.items():

        def _make(skill: str):
            def _prompt() -> str:
                return _skill_text(skill)

            return _prompt

        mcp.prompt(name=prompt_name, description=f"Instructions from the {skill_name} skill")(_make(skill_name))

    return mcp
