# Parts

A part is a module exposing `build(cfg)` that **returns** geometry. See the bundled
skill `bevel-part-authoring` (`bevel skills path`) for the full guide and pitfalls.

```python
import bevel_cad

@bevel_cad.part(name=None, defaults={...}, schema=None, description="...")
def build(cfg): ...
```

- `defaults` — merged as the *part* config layer (below `-c` files and CLI overrides).
- `schema` — optional dataclass extending `BevelSchema` for strict validation of your blocks.
- Accepted return types: `cq.Assembly` (named children → per-body STLs and viewer colours),
  `cq.Shape`, `cq.Workplane`, `trimesh.Trimesh`, anything with `.wrapped`.
- `build` must return the geometry; returning `None` is an error. Anything a part needs to
  do before export (fusing, orienting, segmenting) happens inside `build`.

## Discovery

`bevel list` shows, in precedence order: project `src/` files, `bevel_cad.parts` entry points,
`bevel_cad.providers` (a callable returning `{name: "module.path"}`), bundled examples.

Standalone files are imported with their directory on `sys.path`, so sibling imports work.

## Example project

`examples/` in the bevel-cad repo is a self-contained bevel project (`bevel.yaml`, `configs/`,
`src/`, `renders/`) with `button_label` (engraved plate with a button hole, two bodies) and
`spacer_washer` (inch-dimensioned filleted washer):

```bash
cd examples
bevel list
bevel render button_label_custom          # configs/button_label_custom.yaml -> src/button_label.py
bevel render spacer_washer spacer_washer.outer_diameter_in=2.0
```

Copy the folder anywhere; nothing in it depends on being inside the repository.
