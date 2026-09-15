# Configuration

bevel uses [OmegaConf](https://omegaconf.readthedocs.io/) to merge YAML layers into one
config object with attribute access (`cfg.rendering.exports.stl.enabled`).

## Layers (low → high precedence)

| # | layer | where |
|---|---|---|
| 1 | built-in defaults | `bevel_cad/config/defaults.yaml` |
| 2 | user | `$XDG_CONFIG_HOME/bevel/config.yaml` (`~/.config/bevel/config.yaml`) |
| 3 | project | `bevel.yaml`, found by walking up from cwd (`$BEVEL_ROOT` / `--root` override) |
| 4 | project local | `bevel.local.yaml` next to it (git-ignored) |
| 5 | part defaults | `@bevel_cad.part(defaults=...)` |
| 6 | `-c FILE …` | in the order given; a `.yaml` render target or `configs/<name>.yaml` is appended here |
| 7 | CLI dotlist | `key.path=value` (values parsed as YAML: `true`, `null`, `3.5`, `[a,b]`) |
| 8 | programmatic | `load_layers(overrides=...)` |

`bevel config [TARGET]` prints the merged result; `<stem>.yaml` in every bundle is the
snapshot that produced that render (re-run with `bevel render -c <stem>.yaml`).

## Typed blocks

```yaml
project:
  name: my_project
  description: ...
  configs_dir: configs      # or a list
  src_dir: src              # null: no project sources (parts come from entry points / providers)
  hooks: null               # "package.module:ATTR" -> a bevel_cad.commands.Hooks (see below)

rendering:
  name: null                # run name; falls back to the part name
  output_dir: renders       # relative to the project root (cwd without a project)
  tolerance: 0.001          # tessellation (mm)
  angular_tolerance: 0.05
  exports:                  # mapping keyed by job name
    stl:     {enabled: true, stl_ascii: false}
    step:    {enabled: false, write_pcurves: true, precision_mode: 0}
    "3mf":   {enabled: false}
    glb:     {enabled: true}
    gltf:    {enabled: false}
    obj:     {enabled: false, unit_scale_mm_to_m: true, target_face_count: null, watertight_required: false}
    preview: {enabled: true, image_width: 800, image_height: 600, elevation: 30, azimuth: 45, roll: 0,
              light_azimuth: 225, light_elevation: 45, color: "#b3b3b3", background: "#1a1a2e", opacity: 1.0}
    config:  {enabled: true}
    stats:   {enabled: true}
    iso:     {format: preview, filename: "{name}-iso.png", azimuth: 135}   # extra jobs: any name

viewer:
  enabled: false            # or --viewer
  host: localhost
  port: 32323
  upload_timeout: 300.0
  post_timeout: 60.0
  tolerance: 0.05           # coarser tessellation for the viewer
  angular_tolerance: 0.1
  style: {protocol: null, texture: null, color_faces: null, color_edges: null, color_vertices: null}
```

Export jobs: `format` defaults to the key, `filename` to `{name}.<ext>` where `{name}` is the
bundle stem and `{run_name}` the raw run name. Jobs run in a fixed order
(step, stl, 3mf, glb, gltf, obj, preview, config, stats); `preview`/`obj`/`gltf` synthesise a
disabled GLB job when GLB is off. Two jobs resolving to the same file is an error.

Typed blocks reject unknown keys and wrong types (`viewer.port=abc` fails at load). All other
top-level keys are free-form for parts. The merged config is **struct**: a missing attribute
raises `ConfigAttributeError` (an `AttributeError`) instead of returning `None`; use
`cfg.get("key", default)`.

## Extending with a schema

```python
from dataclasses import dataclass, field
from bevel_cad import BevelSchema

@dataclass
class Bounds: width: float = 100.0; height: float = 100.0

@dataclass
class MySchema(BevelSchema):
    output_bounds: Bounds = field(default_factory=Bounds)

cfg = load_config(schema=MySchema, files=["configs/x.yaml"])
```

Validation in `__post_init__` runs when you call `OmegaConf.to_object(cfg.output_bounds)`.

## Project hooks

A project built on bevel can extend every command by declaring hooks in `bevel.yaml`:

```yaml
project:
  hooks: my_project.bevel_hooks:HOOKS
```

`ATTR` is a `bevel_cad.commands.Hooks` instance (or a zero-argument callable returning one).
Whenever the CLI, the MCP server, or `bevel_cad.commands` is called without explicit
`hooks`, the project's hooks are imported and used; a declaration that fails to import is a
`ConfigError`, never ignored. Hooks can supply:

| field | purpose |
|---|---|
| `schema` | a `BevelSchema` subclass every layer is validated against |
| `prepare_config(cfg, loaded, run)` | turn the merged config into whatever `build()` should receive (a typed wrapper, say) — it shares the run's stats and bundle |
| `resolve_target(cfg, layout)` | pick the part when no target and no `part:` key is given |
| `add_render_flags(parser)` / `render_overrides(args)` | add flags to `bevel render` and map them to dotlist overrides |
| `stage_descriptions` | readable names for `stats.record_stage(...)` entries in the CSV/log |

## One shape per block

Older layouts (`server:` instead of `viewer:`, list-form `rendering.exports`) are rejected
with a `ConfigError` naming the current key; nothing is converted on load. The local override
file is always `bevel.local.yaml` next to the project file, also when `project_config` names a
file with another name.
