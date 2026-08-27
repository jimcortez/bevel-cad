# MCP server

`bevel mcp` exposes every command as typed MCP tools (official `mcp` Python SDK v2).

```bash
pip install "bevel-cad[mcp]"
bevel mcp --root /path/to/project                       # stdio (Claude Code / Desktop)
bevel mcp --transport streamable-http --port 8765       # HTTP
uv run mcp dev src/bevel_cad/mcp/server.py              # MCP Inspector
```

Claude Code:

```bash
claude mcp add bevel -- uv run --directory /path/to/project bevel mcp --root .
```

## Tools

`project_info`, `list_parts`, `describe_part(name)`, `read_part_source(name)`,
`resolve_config(target, configs, overrides)`, `render(target, configs, overrides, name, only,
skip, viewer, out)`, `get_preview(bundle)` → image, `inspect_mesh(path)`, `list_renders(limit)`,
`describe_render(bundle)`, `upload(bundle, name)`, `list_templates`, `create_project(...)`,
`add_part(...)`, `list_skills`, `read_skill(name)`.

`render` runs in a subprocess (`bevel render --json`), so OCC crashes cannot take the server
down; log lines are forwarded as progress. Results are the same JSON the CLI prints with `--json`.

## Resources

`bevel://project`, `bevel://parts/{name}`, `bevel://renders/{stem}/config|stats|log`,
`bevel://skills/{name}`.

## Prompts

`build_part`, `verify_render`, `iterate_model` return the matching skill text.
