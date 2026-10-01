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

bevel imports `cadquery_web_viewer` (2.3+, from PyPI) to tessellate `<stem>.viewer.glb` (one node
per part) and uploads it over HTTP to a viewer you run separately. To develop against an
unreleased viewer, install the sibling checkout into bevel's environment:

```bash
uv sync --extra dev
uv pip install -e ../cadquery-web-viewer
# the viewer pulls in cadquery-ocp-novtk, whose OCP wheel overwrites cadquery's; put it back
# (pinned to the locked version: an unpinned reinstall pulls a newer OCP that cadquery rejects):
uv pip install --reinstall --no-deps "cadquery-ocp==$(uv pip show cadquery-ocp | awk '/^Version:/ {print $2}')"
uv run --no-sync pytest            # --no-sync keeps the editable viewer
cd ../cadquery-web-viewer && uv run cadquery-web-viewer
cd ../bevel-cad && uv run --no-sync bevel render <part> --viewer
```

### The two OCP wheels

cadquery needs `cadquery-ocp` (the VTK build); cadquery-web-viewer pulls in build123d, which needs
`cadquery-ocp-novtk`. Both wheels write the same files into `site-packages/OCP/`, and uv installs
them in parallel, so whichever lands last wins. If `import cadquery` fails with
`cannot import name 'IVtkOCC_Shape' from 'OCP.IVtkOCC'`, the novtk build won. Put the VTK build
back on top with a sync that reinstalls only that package at the locked version:

```bash
uv sync --extra dev --reinstall-package cadquery-ocp
```

CI runs exactly that after every `uv sync`, and the wheel smoke test does the `uv pip` equivalent.
build123d and the viewer run fine on the VTK build.

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
