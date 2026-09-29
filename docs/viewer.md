# cadquery-web-viewer integration

bevel depends on [cadquery-web-viewer](https://github.com/jimcortez/cadquery-web-viewer) (2.2+
is build123d 0.11 / OCP 7.9 and coexists with cadquery 2.8; assembly support lands in 2.3) and
talks to a viewer you run separately:

```bash
cadquery-web-viewer --host localhost --port 32323
bevel render widget --viewer          # or viewer.enabled=true in bevel.yaml
bevel upload renders/widget_20260827-101500
```

## One assembly object per render

Every render is uploaded as **one** viewer object -- an assembly with one named part per body:

- a `cq.Assembly` contributes one part per body (traverse order, node locations applied);
- a single solid, Workplane, build123d object or `trimesh.Trimesh` is an assembly with one
  part named after the run.

In the browser the object appears as one row with its parts nested under it. Parts can be
shown/hidden and recoloured individually; removal and versioning happen for the whole assembly
(pushing the same run name again creates a new version).

The bytes sent are `<stem>.viewer.glb` from the bundle (written by the `viewer` export job, on
by default, and synthesised when `--viewer` is used with the job disabled). It is tessellated by
the viewer package itself -- faces, edges and vertices, one glTF node per part -- so the browser's
edge/vertex tools work, and `bevel render --viewer` and `bevel upload` show exactly the same
thing. `<stem>.assembly.json` next to it lists the parts:

```json
{"schema": 1, "name": "k6_1", "tags": ["bevel", "part:k6_1"],
 "parts": [{"name": "segment_00", "index": 0, "color": "#e04a4a", "tags": ["body:segment_00", "index:0"]}, ...]}
```

Bundles without these two files (rendered before assembly uploads, or with the `viewer` export
disabled and no `--viewer`) cannot be uploaded; `bevel upload` says so and asks for a re-render.
`bevel upload --name X` renames the viewer object (the manifest embedded in the GLB keeps the
original run name; the browser uses the object name).

## Colours and tags

```yaml
viewer:
  colors:
    mode: auto          # auto | manual | off
    base: null          # palette base; null -> preview colour (rendering.exports.preview.color)
    parts: {}           # part name -> "#rrggbb" (override single parts in auto; required for all in manual)
  tags: [rev-b]         # assembly-level tags
  part_tags:            # per-part extra tags
    segment_00: [first]
```

- `auto` (default): evenly spaced hues around the wheel from `base` (complementary for two
  parts, a triad for three, ...); the same palette every render, so parts keep their colours
  across versions. Entries in `parts` pin single parts.
- `manual`: every part must be listed in `parts`; unknown part names are a config error.
- `off`: no colour is sent; the viewer's default face colour applies.

Colours accept `#rrggbb`, CSS names or RGB triples. On the command line, quote hex values so the
`#` is not read as a YAML comment: `bevel render k6_1 'viewer.colors.parts.segment_00="#ff0000"'`.
Note `mode: off` is read by YAML as `false`; bevel maps it back to `off`.

Every part is tagged `body:<name>` and `index:<n>`; the assembly is tagged `bevel` and
`part:<target>`. Tags are informational (shown in the viewer's inspector).

## Behaviour

- reachability is probed (`GET /api/scene`) **before** any file is written; if the viewer is
  down bevel exits 1 with the exact start command and no partial bundle;
- files are written first, the viewer push is always last;
- the uploaded object gets notes/settings (`bevel.run_name`, `bevel.stem`, `bevel.bundle_dir`,
  `bevel.part`, `bevel.parts`, `bevel.part_count`) so you can trace it back to its bundle;
- `viewer.style.*` maps to the `CADQUERY_WEB_VIEWER_*` environment variables.

Python: `bevel_cad.viewer.push_assembly`, `push_artifacts`, `upload_bundle`, `ensure_reachable`;
`bevel_cad.render.assembly.build_manifest` / `AssemblyManifest`;
`bevel_cad.render.viewer_glb.build_viewer_glb`.
