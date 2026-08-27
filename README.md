# bevel-cad

*WARNING: project under active development and not stable at all*

Render, export, and configure [CadQuery](https://cadquery.readthedocs.io/) parts.

`bevel` turns a `build(cfg)` function into a **render bundle** — a timestamped folder with
STL / STEP / 3MF / GLB / GLTF / OBJ exports, a preview PNG, the exact config that produced
it, timings, and a log — and can push the geometry to
[cadquery-web-viewer](https://github.com/jimcortez/cadquery-web-viewer). Configuration is
layered YAML (OmegaConf) with `key.path=value` overrides; a project is a `bevel.yaml` plus
`configs/` and `src/` folders; everything is available as a CLI, a Python API, and an MCP
server so AI assistants can drive it.

```bash
pip install "bevel-cad[viewer,mcp]"        # or: uv add bevel-cad

bevel create my_block --template basic     # scaffold a project (interactive if args omitted)
cd my_block
bevel render my_block                      # -> renders/my_block_<YYYYMMDD-HHMMSS>/
bevel render my_block my_block.cylinder_depth=null --skip preview   # override + faster loop
bevel inspect renders/*/my_block_*.stl     # watertight? components? open edges?
bevel render my_block --viewer             # push to a running cadquery-web-viewer
bevel mcp                                  # expose all of the above to an AI agent
```

## A part

```python
import cadquery as cq
import bevel_cad

@bevel_cad.part(defaults={"widget": {"width": 40.0, "hole_d": 6.0}})
def build(cfg) -> cq.Workplane:
    p = cfg.widget
    return cq.Workplane("XY").box(p.width, p.width, 5).faces(">Z").workplane().hole(p.hole_d)
```

Return an `Assembly` with named children to get one STL per body (and per-body colours in
the viewer). Anything with `.wrapped` (build123d) or a `trimesh.Trimesh` works too.

## Python API

```python
from bevel_cad import load_config, render_part

cfg = load_config(files=["configs/widget.yaml"], dotlist=["widget.hole_d=8"])
result = render_part(build(cfg), cfg, name="widget-8mm")
print(result.bundle_dir, result.path_for("stl"), result.extra_paths)
```

## Project layout

```
bevel.yaml            project config: how to render (formats, tolerances, viewer)
bevel.local.yaml      personal overrides (git-ignored)
configs/<part>.yaml   per-part config: `part:` + the part's block
src/<part>.py         build(cfg) -> geometry
renders/<slug>_<ts>/  bundles
```

Config layers, low to high: built-in defaults → `~/.config/bevel/config.yaml` →
`bevel.yaml` → `bevel.local.yaml` → part `defaults=` → `-c FILE …` → `KEY=VALUE`.
The `project`, `rendering`, and `viewer` blocks are typed and validated; everything else is
free-form. Missing keys raise (no silent `None`); use `cfg.get("key", default)` for optional ones.

## Commands

| command | |
|---|---|
| `bevel render [TARGET] [-c FILE]… [KEY=VALUE]… [--name N] [--out DIR] [--only F] [--skip F] [--viewer]` | build + bundle |
| `bevel config [TARGET] …` | print the merged config |
| `bevel list` / `bevel describe NAME` | discoverable parts and their defaults |
| `bevel renders` / `bevel show BUNDLE` | previous bundles; files, snapshot, stats, log |
| `bevel inspect MESH…` | watertight, components, boundary/non-manifold edges, volume |
| `bevel upload BUNDLE` | re-push a bundle to the viewer |
| `bevel create` / `bevel add` / `bevel templates` | scaffolding (`basic`, `label`) |
| `bevel skills list\|install` | agent skills for building/verifying parts |
| `bevel mcp [--transport stdio\|streamable-http]` | MCP server |

Every command takes `--root DIR` and `--json`. `TARGET` is a `.py`/`.yaml` path, a project part
name, `pkg.module[:fn]`, or a registered name (`bevel_cad.parts` / `bevel_cad.providers` entry points).
A ready-made project lives in [examples/](examples/).

## Docs

[docs/config.md](docs/config.md) · [docs/cli.md](docs/cli.md) · [docs/parts.md](docs/parts.md) ·
[docs/project-layout.md](docs/project-layout.md) · [docs/viewer.md](docs/viewer.md) ·
[docs/mcp.md](docs/mcp.md) · [docs/skills.md](docs/skills.md)

## Extending

Other packages register parts via entry points and can add typed config blocks / CLI flags:

```toml
[project.entry-points."bevel_cad.parts"]
clamp = "mypkg.parts.clamp"
[project.entry-points."bevel_cad.providers"]
mypkg = "mypkg.registry:bevel_parts"      # -> {name: "module.path", ...}
```

```python
from bevel_cad.cli import CliHooks, main
main(hooks=CliHooks(schema=MySchema, add_render_flags=add_my_flags, prepare_config=wrap_cfg))
```

MIT licensed. Python 3.10–3.12 (the viewer pins `<3.13`).
