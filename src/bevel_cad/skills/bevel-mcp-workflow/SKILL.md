---
name: bevel-mcp-workflow
description: Best practices for driving bevel through its MCP server (bevel mcp) — which tools to call in which order to build, render, inspect, and view CadQuery parts reliably, how to read results, handle long renders and failures, and report outcomes.
---

# Working through the bevel MCP server

The server (`bevel mcp --root <project>`) exposes the same commands as the CLI with typed
arguments and structured results. Everything is scoped to one project root.

## Tool map

| tool | use it to |
|---|---|
| `project_info` / resource `bevel://project` | confirm root, layout, resolved project config |
| `list_parts` | what can be rendered (project `src/`, registered, examples) |
| `describe_part(name)` / `read_part_source(name)` | learn a part's config block + defaults before changing anything |
| `resolve_config(target, configs, overrides)` | see the exact merged config a render would use |
| `render(target, overrides, skip, only, name, viewer)` | build + write a bundle; returns files, stats, warnings |
| `inspect_mesh(path)` | watertight / components / open edges / volume / extents |
| `get_preview(bundle)` | the preview PNG as an image — look at it |
| `list_renders` / `describe_render(bundle)` | find previous bundles; read snapshot, stats, log tail |
| `upload(bundle)` | push a bundle to cadquery-web-viewer |
| `list_templates` / `create_project` / `add_part` | scaffold new work |

## The reliable sequence

1. `list_parts` -> pick the target; `describe_part` to get its config keys and defaults.
2. Edit code/config with your file tools (parts live in `src/`, config in `configs/`).
3. `resolve_config(target)` — check the merged values before spending a render.
4. `render(target, skip=["preview", "stats"])` while iterating; a full `render(target)` once
   the shape is right. Use `overrides={"widget.hole_d": 8}` for experiments, `name=` to label runs.
5. `inspect_mesh` on the merged STL **and** each `extra_files` per-body STL from the result.
6. `get_preview(bundle)` and actually look at the image; compare with the intent.
7. Only then `upload(bundle)` / `render(..., viewer=True)` for human review.
8. Report: bundle path, files, key stats (`render.total.duration_s`), inspect verdicts, and
   anything you changed.

## Reading a `render` result

`files` maps job name -> path; `extra_files` are per-body STLs; `stats` includes timings,
`git.commit`, and every config source layer; `viewer_names` is non-empty only when pushed.
`bundle_dir: null` means nothing was written (all exports disabled or a legacy part).

## Failures

- `ViewerUnreachable`: start `cadquery-web-viewer --host … --port …` (message says which) or
  render with `viewer=False`; no partial bundle is written.
- A `ValueError` from the part = your parameters are geometrically impossible; the message
  names the parameter. Fix the config, don't retry blindly.
- OCC/boolean errors: change the construction (open the loop, reorder chamfer/cut, over-
  extend and trim) — repeating the same operation with nudged values rarely helps.
- Watertight/component failures: see **bevel-render-verify**; the part is not printable yet.

## Long renders

Rendering runs in a subprocess; the server streams log lines as progress. Skip previews and
extra formats while iterating, and prefer coarser geometry (fewer segments/strands) for test
renders, then do one full-quality run at the end.
