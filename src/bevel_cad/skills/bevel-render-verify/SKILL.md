---
name: bevel-render-verify
description: The render -> inspect -> look loop for bevel parts — fast iteration flags, reading a render bundle (STL/GLB/PNG/YAML/CSV/log), mesh checks with bevel inspect, and the acceptance checklist before calling a model done. Use after editing a part or its config.
---

# Render and verify a bevel part

## 1. Fast loop while the geometry is still moving

```bash
bevel render <part> --skip preview,stats      # STL + GLB + config only; seconds, no GL
bevel render <part> <part>.some_key=12.5      # try a value without editing files
bevel render <part> --only step               # one format when that is all you need
```

Every run creates `renders/<slug>_<YYYYMMDD-HHMMSS>/` — nothing is overwritten, so
compare runs side by side. `--name foo` makes related runs easy to spot.

## 2. Full render, then read the bundle

```bash
bevel render <part>
bevel renders                 # newest first
bevel show <stem>             # files, config snapshot, timings, log tail
```

A complete bundle contains, all sharing the stem:

| file | what to check |
|---|---|
| `<stem>.stl` | merged mesh -> `bevel inspect` |
| `<stem>_<body>.stl` | one per named body (assemblies) -> inspect each |
| `<stem>.glb` | what the viewer/preview use |
| `<stem>.png` | **open it and look** (see 3) |
| `<stem>.yaml` | the exact config that produced this; re-run with `bevel render -c <stem>.yaml` |
| `<stem>.csv` | stage timings, git commit, config sources |
| `<stem>.log` | full DEBUG log; first place to look when something is off |

## 3. Look at the preview — always

Open `<stem>.png`. Geometry bugs (missing cut, mirrored text, pocket on the wrong face,
letters floating) are obvious in the image and invisible in a passing mesh check. If the
angle hides the feature, add a second view in `bevel.yaml`:

```yaml
rendering:
  exports:
    iso_back: {format: preview, filename: "{name}-back.png", azimuth: 225, elevation: 20}
```

## 4. Mesh checks

```bash
bevel inspect renders/<stem>/<stem>.stl renders/<stem>/<stem>_*.stl
```

Pass criteria per body: `Watertight: True`, `Components: 1`, `Boundary edges: 0`,
`Non-manifold edges: 0`, volume in the expected range. Anything else is not printable:
go back to the part (see the pitfalls reference in **bevel-part-authoring**).

Also sanity-check dimensions: the extents printed by `bevel inspect` must match the
design intent (a 50 mm block is 50 x 50 x 50, a plate is `thickness` tall).

## 5. Viewer (optional, for interactive inspection)

Start `cadquery-web-viewer` in another terminal, then `bevel render <part> --viewer` or
`bevel upload renders/<stem>`. Multi-body assemblies arrive as separately coloured objects.
If the viewer is down, bevel exits 1 with the start command — it never writes a partial bundle.

## Acceptance checklist

- [ ] Preview PNG looked at; every feature present and on the intended face/side.
- [ ] `bevel inspect` clean for the merged STL and every per-body STL.
- [ ] Extents/volume match the design numbers.
- [ ] `<stem>.yaml` snapshot has the values you meant (no stale override from a `-c` file).
- [ ] Log has no `WARNING`/`ERROR` lines you cannot explain.
- [ ] Multi-material parts: bodies don't overlap (fuse volume == sum of volumes).
