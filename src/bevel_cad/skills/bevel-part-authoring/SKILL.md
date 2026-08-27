---
name: bevel-part-authoring
description: How to write a CadQuery part for a bevel project — the build(cfg) contract, project layout, config blocks and defaults, naming bodies, validation, and CadQuery/OCC pitfalls learned the hard way. Use when creating or editing src/<part>.py in a project that has a bevel.yaml.
---

# Authoring a bevel part

A **part** is a Python module in `src/` that exposes `build(cfg)` and *returns* CadQuery
geometry. bevel does everything after that: exports, preview, bundle folder, config
snapshot, stats, log, viewer push. Never call export functions from a part.

## Project layout (created by `bevel create`)

```
bevel.yaml           project-wide "how to render" (formats, tolerances, viewer)
configs/<part>.yaml  what to build: `part:` + the part's own config block
src/<part>.py        build(cfg) -> geometry
renders/<slug>_<ts>/ output bundles (never edit by hand)
```

`bevel render <name>` looks up `configs/<name>.yaml` (its `part:` key names the source,
default `<name>`), then `src/<name>.py`, then importable modules / registered parts.

## The contract

```python
from typing import Any
import cadquery as cq
import bevel_cad

DEFAULTS = {"widget": {"width": 40.0, "hole_d": 6.0}}          # one block, named like the part

def build_widget(width: float, hole_d: float) -> cq.Workplane:  # pure, testable, no config
    if hole_d >= width:
        raise ValueError("hole_d must be smaller than width.")  # fail early, in mm
    return cq.Workplane("XY").box(width, width, 5).faces(">Z").workplane().hole(hole_d)

@bevel_cad.part(defaults=DEFAULTS, description="Square plate with a centre hole")
def build(cfg: Any) -> cq.Workplane:                           # thin adapter: config -> builder
    p = cfg.widget
    return build_widget(float(p.width), float(p.hole_d))
```

Rules that keep parts reusable:

- **Return** `cq.Assembly`, `cq.Shape` (Solid/Compound), `cq.Workplane`, or a `trimesh.Trimesh`.
  build123d objects work too (anything with `.wrapped`).
- Keep geometry code in pure functions that take primitives; `build(cfg)` only reads config.
- Put every tunable in one config block named after the part and declare it in
  `@bevel_cad.part(defaults=...)`. Defaults merge *below* `configs/<part>.yaml` and CLI
  overrides, so users can change anything with `bevel render widget widget.hole_d=8`.
- Read config with attribute access (`cfg.widget.width`); the config is strict, so a typo
  raises instead of silently returning `None`. Use `cfg.get("optional_block")` for optional keys.
- Units are millimetres. Convert at the edge if the design is specified in inches.
- Validate arguments with `ValueError` messages that name the parameter.

## Multi-body parts: name the bodies

Return a `cq.Assembly` with one named child per printable body:

```python
assy = cq.Assembly(name="Label")
assy = assy.add(plate, name="plate")
assy = assy.add(letters, name="text_fill")
return assy
```

bevel writes `<stem>_plate.stl`, `<stem>_text_fill.stl` next to the merged STL (slice each in
its own colour) and pushes each body to the viewer in its own colour. Body names must be
unique after slugging. A frozen dataclass of solids with a `to_assembly()` method is the
tidy pattern (see `bevel_cad.examples.button_label`).

## Style used across the bundled examples

- `from cadquery.func import *`-style functional API (`box`, `extrude`, `cut`, `fuse`,
  `clean`, `text`, `fillet2D`) for parametric geometry; `cq.Workplane` chains for selectors
  (`faces(">Z").edges().chamfer(...)`).
- `clean()` results after boolean chains before returning or measuring volumes.
- Text: `bevel_cad.geom.text_plate` has plate/engrave helpers; `DejaVu Sans` is the safe
  default font on Linux (has arrows, accents). Empty text geometry means the font/glyph is
  missing — the helper raises.
- Fuse many small solids with `bevel_cad.mesh.fuse.fuse_part_solids` (map-reduce, asserts
  a single lump); check watertightness with `bevel_cad.mesh.validate.require_watertight`.

Read `references/cadquery-pitfalls.md` before doing sweeps, booleans on closed loops, or
anything that produced "invalid shape" / non-watertight meshes. A minimal skeleton is in
`references/part-skeleton.py`.

## Checklist before rendering

1. `build()` returns geometry (not `None`), bodies named, dimensions validated.
2. Config block declared in `defaults=`; `configs/<part>.yaml` only overrides what differs.
3. `bevel config <part>` shows the merged values you expect.
4. Follow **bevel-render-verify** for the render/inspect loop.
