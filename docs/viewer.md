# cadquery-web-viewer integration

Install with `pip install "bevel-cad[viewer]"` and run the viewer separately:

```bash
cadquery-web-viewer --host localhost --port 32323
bevel render widget --viewer          # or viewer.enabled=true in bevel.yaml
bevel upload renders/widget_20260827-101500
```

Behaviour:

- reachability is probed (`GET /api/scene`) **before** any file is written; if the viewer is
  down bevel exits 1 with the exact start command and no partial bundle;
- files are written first, the viewer push is always last;
- assemblies with ≥ 2 bodies are uploaded as separately coloured objects (palette derived
  from the preview colour); single bodies upload the bundle GLB as one object;
- every uploaded object gets notes/settings (`bevel.run_name`, `bevel.stem`,
  `bevel.bundle_dir`, `bevel.part`) so you can trace a viewer object back to its bundle;
- `viewer.style.*` maps to the `CADQUERY_WEB_VIEWER_*` environment variables.

Python: `bevel_cad.viewer.push_glb`, `push_colored_parts`, `upload_bundle`, `ensure_reachable`.
