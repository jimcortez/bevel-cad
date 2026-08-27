# Project layout

```
my_project/
  bevel.yaml            project config (typed blocks project/rendering/viewer + anything shared)
  bevel.local.yaml      personal overrides, git-ignored
  configs/<part>.yaml   per-part: `part: <source>` + the part's own block
  src/<part>.py         part sources (src/ is put on sys.path)
  renders/<slug>_<YYYYMMDD-HHMMSS>/
      <stem>.stl  <stem>_<body>.stl  <stem>.glb  <stem>.png  <stem>.yaml  <stem>.csv  <stem>.log
      [<stem>.step  <stem>.3mf  <stem>.gltf  <stem>.obj]
  .claude/skills/bevel-*/   agent skills (bevel skills install --project)
```

- Root discovery: walk up from cwd for `bevel.yaml`; `$BEVEL_ROOT` or `--root` override.
- `project.configs_dir` may be a list (e.g. `[knot_configs, part_configs]`).
- `rendering.output_dir` resolves against the root (against cwd when there is no project).
- `bevel create NAME` scaffolds all of this plus a first part from a template;
  `bevel add NAME` adds another config/source pair.
