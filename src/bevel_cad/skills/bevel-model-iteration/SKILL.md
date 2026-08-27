---
name: bevel-model-iteration
description: How to change and evolve a bevel model safely — config layers vs code changes, dotlist overrides, local overrides, naming runs so bundles are comparable, comparing renders, keeping design notes, and when to add a new part or template instead of a config variant.
---

# Iterating on a bevel model

## Change the config before changing the code

Most tweaks are numbers. Try them without touching source:

```bash
bevel render widget widget.hole_d=8                # one-off override (highest precedence)
bevel render widget -c configs/widget_big.yaml     # a saved variant layered on top
bevel config widget widget.hole_d=8                # see the merged result first
```

Precedence, low -> high: built-in defaults -> `bevel.yaml` -> `bevel.local.yaml` (git-ignored,
personal) -> part `defaults=` -> `configs/<part>.yaml` / `-c FILE` (in order) -> `KEY=VALUE`.

Only edit `src/<part>.py` when the *shape* changes (new feature, different construction)
or a value needs to become a parameter — then add it to `DEFAULTS` **and** document it in
the module docstring so `bevel describe <part>` shows it.

## Make runs comparable

- `bevel render widget --name widget-hole8` -> `renders/widget-hole8_<ts>/`.
- Keep the same export set between runs you intend to compare.
- Compare with `bevel inspect a.stl b.stl` (volume/extents) and the two PNGs side by side.
- `bevel show <stem>` prints the snapshot config: diff two snapshots to see exactly what changed.

## Keep the notebook in the YAML

`configs/<part>.yaml` supports comments — record why a value is what it is and what failed:

```yaml
widget:
  hole_d: 8.0     # 6.0 too tight for M6 after resin shrink (tested 2026-08-20)
  # 2026-08-21: tried chamfer 1.2 -> pocket wall broke through; keep <= 0.8
```

Snapshots in `renders/` are immutable evidence; the config file is the living record.

## Variant vs new part vs template

| you want | do |
|---|---|
| same code, different numbers/text | a second config: `configs/widget_v2.yaml` with `part: widget` |
| same idea, extra feature | add a parameter with a safe default to the existing part |
| different construction entirely | `bevel add newpart --template basic` and start clean |
| many projects will start from this shape | turn it into a template (`bevel_cad/templates/<name>/`) |

## Re-running old work

`bevel render -c renders/<stem>/<stem>.yaml` reproduces a bundle from its snapshot
(the snapshot pins `part:` and `rendering.name`). `bevel upload renders/<stem>` pushes an
old bundle to the viewer without rebuilding.

## Don't
- Don't loop on the same failing OCC operation with slightly different numbers; if a boolean
  or sweep fails twice, change the construction (see pitfalls in **bevel-part-authoring**).
- Don't edit files inside `renders/`.
- Don't put project-wide settings (formats, viewer host) in a part config; that is `bevel.yaml`.
