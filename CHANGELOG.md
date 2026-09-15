# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/jimcortez/bevel-cad/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/jimcortez/bevel-cad/releases/tag/v0.1.0
