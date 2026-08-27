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
- Returning `None` means "the part rendered itself" (legacy contract); nothing is written.

## Discovery

`bevel list` shows, in precedence order: project `src/` files, `bevel_cad.parts` entry points,
`bevel_cad.providers` (a callable returning `{name: "module.path"}`), bundled examples.

Standalone files are imported with their directory on `sys.path`, so sibling imports work.

## Examples shipped with bevel-cad

`button_label`, `button_label_power`, `button_label_volume`, `button_label_spicy_family`
(engraved plates with a button hole, two bodies), `planet_spacer` (inch-dimensioned washer),
`finger_sensor_holder` (hinged pulse-sensor cradle, validated watertight). Run them from the
`examples/` project: `cd examples && bevel render button_label_custom`.
