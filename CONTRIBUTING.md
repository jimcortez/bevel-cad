# Contributing to bevel-cad

Thanks for helping out. This is a small project with one maintainer, so keep changes focused
and open an issue first for anything large.

## Setup

```bash
git clone git@github.com:jimcortez/bevel-cad.git
cd bevel-cad
uv sync --extra dev
uv run bevel --version
```

`uv` manages the virtualenv and the lock file. Python 3.11 or 3.12 is required
(cadquery 2.8 needs 3.11; the viewer pins `<3.13`).

## Commands you should know

| Task | Command |
|------|---------|
| Lint | `uv run ruff check .` |
| Auto-fix lint / import order | `uv run ruff check --fix .` |
| Type check | `uv run pyright` |
| Tests | `uv run pytest` |
| Tests, requiring the preview PNG path to work | `BEVEL_CI_REQUIRE_PREVIEW=1 uv run pytest` |
| Build wheel + sdist | `uv build && uvx twine check --strict dist/*` |
| Render the example project | `cd examples && uv run bevel render button_label` |

CI (`.github/workflows/ci.yml`) runs exactly these: the reusable build workflow builds the
distributions, installs the wheel in a clean environment and exercises the CLI, and the test
matrix runs ruff, pyright and pytest on Linux 3.11/3.12 plus macOS and Windows 3.12.

Preview PNGs render through pyrender on EGL. On a headless Linux box install
`libegl1 libgl1 libgles2 libgl1-mesa-dri libosmesa6` (and `fonts-dejavu-core` for the text
parts). Without a GL stack the single preview test skips.

## Working against a local cadquery-web-viewer checkout

bevel imports `cadquery_web_viewer` to tessellate `<stem>.viewer.glb` (one node per part) and
uploads it over HTTP to a viewer you run separately. Assembly support (`AssemblySpec`,
`prepare_assembly_upload`) is in the viewer's `main` ahead of its 2.3 release, so install the
sibling checkout into bevel's environment:

```bash
uv sync --extra dev
uv pip install -e ../cadquery-web-viewer
# the viewer pulls in cadquery-ocp-novtk, whose OCP wheel overwrites cadquery's; put it back:
uv pip install --reinstall --no-deps cadquery-ocp
uv run --no-sync pytest            # --no-sync keeps the editable viewer
cd ../cadquery-web-viewer && uv run cadquery-web-viewer
cd ../bevel-cad && uv run --no-sync bevel render <part> --viewer
```

Once cadquery-web-viewer 2.3 is on PyPI, bump the pin to `>=2.3` and drop the editable install.

## Pull request expectations

Before opening a PR run the three quality gates locally:

```bash
uv run ruff check .
uv run pyright
uv run pytest
```

PRs that change the CLI, config keys, or the MCP tools should update the matching page under
`docs/`. PRs that add or remove user-visible behaviour should add a line to `CHANGELOG.md`
under *Unreleased*.

Branches: feature branches off `main`, short kebab-case names. All GitHub Actions in
`.github/workflows` are pinned to commit SHAs; Dependabot keeps them current.

## Releasing

See [docs/releasing.md](docs/releasing.md). Short version: `git tag -a vX.Y.Z -m vX.Y.Z && git push origin vX.Y.Z`.
