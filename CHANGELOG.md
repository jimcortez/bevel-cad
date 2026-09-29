# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `lxml` is a core dependency (trimesh's 3MF exporter needs it).
- `manifold3d>=3.5` is a core dependency: exact mesh booleans, `split_by_plane` and
  `minkowski_sum` for parts that work in the mesh domain (also trimesh's boolean engine).
- Viewer assemblies: every render is pushed to cadquery-web-viewer as **one** object with one
  named part per body (a single solid is a one-part assembly). Parts can be shown/hidden and
  recoloured individually in the browser; removal and versions apply to the whole object.
- `viewer` export job (on by default): `<stem>.viewer.glb` (tessellated by the viewer package,
  one glTF node per part) plus `<stem>.assembly.json`. `--viewer` synthesises the job when the
  export is disabled. `bevel upload` sends these two files.
- `viewer.colors` (`mode: auto | manual | off`, `base`, per-part `parts`), `viewer.tags` and
  `viewer.part_tags`; parts are auto-tagged `body:<name>` / `index:<n>`, assemblies `bevel` /
  `part:<target>`.
- `render` results / JSON gain `viewer_parts`; the uploaded object's settings gain
  `bevel.parts` and `bevel.part_count`.
- `bevel_cad.render.assembly` (`AssemblyManifest`, `build_manifest`, `resolve_part_colors`),
  `bevel_cad.render.viewer_glb.build_viewer_glb`, `bevel_cad.render.errors.ExportError`,
  `bevel_cad.render.naming.name_from_target`.

### Changed

- **Breaking:** `cadquery-web-viewer>=2.2` is a hard dependency (assembly support needs the
  unreleased 2.3 API; install it from a checkout until then).
- **Breaking:** `bevel_cad.viewer.push_glb` and `push_colored_parts` are gone; use
  `push_assembly` / `push_artifacts`. `push_artifacts(ctx, run)` no longer takes `name=` and
  returns the single object name.
- **Breaking:** `RenderBundle` gains `viewer_glb_path` / `assembly_json`; `resolve_render_bundle`
  rejects bundles without them (no fallback to `<stem>.glb`).
- `iter_assembly_leaf_solids` applies node locations (composed with parents), matching
  `Assembly.toCompound()`; per-body STLs of assemblies that use `loc=` move accordingly.

### Fixed

- 3MF export writes closed meshes. CadQuery's 3MF exporter tessellated each face on its own and
  shared no vertices, so slicers reported every face boundary as an open edge (every edge, for
  solids sewn from triangles). `bevel_cad.mesh.threemf` now welds each body with trimesh and
  writes the 3MF with trimesh's exporter, one named object per assembly body; a body from a
  closed solid that does not weld closed fails the export.

## [0.2.0] - 2026-09-14

### Added

- Project-scoped hooks: `project.hooks: package.module:ATTR` in `bevel.yaml` is picked up by
  the CLI, the MCP server, and `bevel_cad.commands` whenever no hooks are passed explicitly.
- `Hooks.render_overrides` maps flags added through `Hooks.add_render_flags` to dotlist
  overrides (those flags were parsed and dropped before).
- `project.src_dir: null` for projects whose parts come only from entry points / providers.
- Public fuse API: `bevel_cad.mesh.fuse_solids_map_reduce`, `assert_single_solid`,
  `release_shapes`; `bevel_cad.mesh` re-exports the mesh helpers.

### Changed

- `build()` must return geometry; returning `None` is a `CommandError`. The "part rendered
  itself" contract and the module-global last-result bookkeeping are gone.
- Configuration is strict about shape: a `server:` block or a list-form `rendering.exports`
  raises `ConfigError` instead of being converted with a `DeprecationWarning`; obsolete export
  keys are no longer silently dropped.
- The local override file is always `bevel.local.yaml`; the `config.yaml` /
  `config.local.yaml` special case is gone.
- A provider entry point that fails to load raises `InvalidPart` instead of logging a warning.

## [0.1.0] - 2026-09-14

### Added

- Render pipeline: `build(cfg)` to a timestamped bundle with STL / STEP / 3MF / GLB / GLTF / OBJ
  exports, preview PNG, config snapshot, stats CSV, and log.
- Layered OmegaConf configuration (`bevel.yaml`, `bevel.local.yaml`, `configs/<part>.yaml`,
  `-c FILE`, `KEY=VALUE` overrides) with typed `project` / `rendering` / `viewer` blocks.
- CLI: `render`, `config`, `list`, `describe`, `renders`, `show`, `inspect`, `upload`, `create`,
  `add`, `templates`, `skills`, `mcp`.
- MCP server (`bevel mcp`) exposing the CLI to AI agents; bundled agent skills.
- Project scaffolding templates (`basic`, `label`) and a self-contained `examples/` project.
- Entry points `bevel_cad.parts` / `bevel_cad.providers` for third-party part registries.

### Changed

- `requires-python` is now `>=3.11,<3.13` and `cadquery>=2.8` (the code uses
  `cadquery.func.fillet2D`, which first shipped in 2.8; 2.8 needs Python 3.11).
- The `viewer` extra is removed until `cadquery-web-viewer` 2.2 is published; the current
  2.1.x release pins an OCP version that cannot coexist with cadquery 2.8.

### CI / packaging

- Version is derived from git tags via hatch-vcs; `bevel --version` reports it.
- GitHub Actions: build + `twine check`, test matrix (Linux 3.11/3.12, macOS 3.12, Windows 3.12),
  ruff, pyright, clean-environment wheel smoke test, weekly CodeQL, Dependabot, Renovate.
- Releases publish to PyPI with Trusted Publishing (PEP 740 attestations) and attach a
  GitHub build-provenance attestation plus the wheel and sdist to the GitHub Release.

[Unreleased]: https://github.com/jimcortez/bevel-cad/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/jimcortez/bevel-cad/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/jimcortez/bevel-cad/releases/tag/v0.1.0
