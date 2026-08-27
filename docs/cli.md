# CLI

All commands accept `--root DIR` (project root; default: nearest `bevel.yaml`), `--json`, `-v`.
Exit codes: `0` ok, `1` user-facing failure (unknown part, invalid config, viewer down,
export error), `2` usage.

```
bevel render [TARGET] [KEY=VALUE]... [-c FILE]... [--name N] [--out DIR]
             [--only FMT[,FMT]] [--skip FMT[,FMT]] [--viewer | --no-viewer]
bevel config [TARGET] [KEY=VALUE]... [-c FILE]...
bevel upload BUNDLE [KEY=VALUE]... [-c FILE]... [--name N]
bevel list                       bevel describe NAME [--source]
bevel renders [--limit N]        bevel show BUNDLE
bevel inspect MESH...            bevel project
bevel create [NAME] [--description D] [--format stl|step|3mf|glb] [--template basic|label]
             [--dir PATH] [--param KEY=VALUE] [-y] [--no-skills] [--force]
bevel add NAME [--template T] [--param KEY=VALUE] [-y] [--force]
bevel templates                  bevel skills list|install|path [--project|--user|--to DIR] [--force]
bevel mcp [--transport stdio|streamable-http] [--host H] [--port P]
```

## TARGET resolution

1. an existing `.py` file, or a `.yaml` file (used as the last config layer; its `part:` key names the code);
2. `<configs_dir>/<name>.yaml` (+ `part:`), then `<src_dir>/<name>.py` in the project;
3. `package.module[:callable]`;
4. a registered name (`bevel_cad.parts` / `bevel_cad.providers` entry points, bundled examples).

Positionals after the target that contain `=` are dotlist overrides.

`--only` enables exactly the listed formats (plus `config` and `stats`); `--skip` disables the
listed ones. Both accept format names (`stl`) or job names (`iso`).

## `--json`

Every command prints a JSON object/array with `--json` — the same data the MCP server returns.
`render` gives `{run_name, stem, bundle_dir, files{job: path}, extra_files[], viewer_names[], stats{}}`.
