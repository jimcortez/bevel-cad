"""argparse front-end over :mod:`bevel_cad.commands`."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

from bevel_cad import __version__, commands
from bevel_cad.commands import CommandError, Hooks

CliHooks = Hooks  # alias: the CLI takes the same hooks object as the command layer

EXIT_OK, EXIT_FAILURE, EXIT_USAGE = 0, 1, 2


def _split_csv(value: Optional[str]) -> List[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _split_positionals(items: Sequence[str]) -> Tuple[Optional[str], List[str]]:
    """First positional without '=' is the target; everything else is a dotlist override."""
    target: Optional[str] = None
    dots: List[str] = []
    for item in items:
        if "=" in item and not Path(item).exists():
            dots.append(item)
        elif target is None:
            target = item
        else:
            dots.append(item)
    return target, dots


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--root", help="project root (default: nearest directory with bevel.yaml)")
    p.add_argument("--json", action="store_true", help="print the result as JSON")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging / tracebacks")


def _add_config_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("-c", "--config", action="append", default=[], metavar="FILE", help="extra config layer (repeatable, in order)")


def build_parser(*, prog: str = "bevel", hooks: Optional[Hooks] = None) -> argparse.ArgumentParser:
    hooks = hooks or Hooks()
    parser = argparse.ArgumentParser(prog=prog, description="Render, export, and configure CadQuery parts.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p = sub.add_parser("render", help="build a part and write its render bundle")
    p.add_argument("items", nargs="*", metavar="TARGET|KEY=VALUE",
                   help="part target (file, name, module) followed by dotlist overrides, e.g. rendering.exports.step.enabled=true")
    _add_config_args(p)
    p.add_argument("--name", help="run name (bundle folder and file stem)")
    p.add_argument("--out", metavar="DIR", help="override rendering.output_dir")
    p.add_argument("--only", metavar="FMT[,FMT]", help="enable only these export formats/jobs (config+stats always kept)")
    p.add_argument("--skip", metavar="FMT[,FMT]", help="disable these export formats/jobs")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--viewer", dest="viewer", action="store_true", default=None, help="push to cadquery-web-viewer")
    g.add_argument("--no-viewer", dest="viewer", action="store_false", help="never push to the viewer")
    _add_common(p)
    if hooks.add_render_flags:
        hooks.add_render_flags(p)

    p = sub.add_parser("config", help="print the fully resolved config as YAML")
    p.add_argument("items", nargs="*", metavar="TARGET|KEY=VALUE")
    _add_config_args(p)
    _add_common(p)

    p = sub.add_parser("upload", help="push an existing render bundle to the viewer")
    p.add_argument("bundle", help="bundle directory or its <stem>.yaml")
    p.add_argument("overrides", nargs="*", metavar="KEY=VALUE")
    _add_config_args(p)
    p.add_argument("--name", help="viewer object name")
    _add_common(p)

    p = sub.add_parser("list", help="list discoverable parts")
    _add_common(p)

    p = sub.add_parser("describe", help="show one part's metadata and defaults")
    p.add_argument("name")
    p.add_argument("--source", action="store_true", help="also print the source file")
    _add_common(p)

    p = sub.add_parser("inspect", help="report mesh watertightness / components / open edges")
    p.add_argument("mesh", nargs="+")
    _add_common(p)

    p = sub.add_parser("renders", help="list render bundles, newest first")
    p.add_argument("--limit", type=int, default=20)
    _add_common(p)

    p = sub.add_parser("show", help="describe one render bundle (files, config, stats, log tail)")
    p.add_argument("bundle", help="bundle dir, stem, or snapshot yaml")
    _add_common(p)

    p = sub.add_parser("project", help="show the detected project root, layout, and config")
    _add_common(p)

    try:  # optional sub-commands registered by other modules
        from bevel_cad.cli import create as _create

        _create.register(sub, _add_common)
    except ImportError:  # pragma: no cover
        pass
    try:
        from bevel_cad.cli import skills as _skills

        _skills.register(sub, _add_common)
    except ImportError:  # pragma: no cover
        pass
    try:
        from bevel_cad.cli import mcp as _mcp

        _mcp.register(sub, _add_common)
    except ImportError:  # pragma: no cover
        pass
    return parser


def _init_logging(verbose: bool) -> None:
    if logging.root.handlers:
        logging.root.setLevel(logging.DEBUG if verbose else logging.INFO)
        return
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format="%(levelname)s:%(name)s:%(message)s")


def _emit(result: Any, as_json: bool, text_fn) -> None:
    if as_json:
        data = result.to_dict() if hasattr(result, "to_dict") else result
        if isinstance(result, list):
            data = [r.to_dict() if hasattr(r, "to_dict") else r for r in result]
        print(json.dumps(data, indent=2, default=str))
    else:
        text_fn(result)


def _render_text(res) -> None:
    if not res.written and not res.viewer_names:
        print("Nothing written (no export jobs enabled).")
        return
    print(f"Render bundle: {res.bundle_dir}")
    for name, path in res.written.items():
        print(f"  {name:8s} {path.name}")
    for p in res.extra_paths:
        print(f"  body     {p.name}")
    if res.viewer_names:
        print(f"  viewer   {', '.join(res.viewer_names)}")


def _dispatch(args: argparse.Namespace, hooks: Hooks) -> int:
    cmd = args.command
    root = getattr(args, "root", None)
    as_json = getattr(args, "json", False)

    if cmd == "render":
        target, dots = _split_positionals(args.items)
        res = commands.render(
            target, configs=args.config, overrides=dots, name=args.name, out=args.out,
            only=_split_csv(args.only), skip=_split_csv(args.skip), viewer=args.viewer, root=root, hooks=hooks,
        )
        _emit(res, as_json, _render_text)
        return EXIT_OK

    if cmd == "config":
        target, dots = _split_positionals(args.items)
        text = commands.resolve_config(target, configs=args.config, overrides=dots, root=root, hooks=hooks)
        if as_json:
            import yaml

            print(json.dumps(yaml.safe_load(text), indent=2, default=str))
        else:
            print(text, end="")
        return EXIT_OK

    if cmd == "upload":
        res = commands.upload(args.bundle, configs=args.config, overrides=args.overrides, name=args.name, root=root)
        _emit(res, as_json, lambda r: print(f"Uploaded {r.stem} as {', '.join(r.viewer_names)} -> {r.viewer_url}"))
        return EXIT_OK

    if cmd == "list":
        parts = commands.list_parts(root=root, hooks=hooks)

        def _text1(items):
            if not items:
                print("No parts found.")
            for p in items:
                print(f"{p.name:32s} {p.kind:12s} {p.location}")

        _emit(parts, as_json, _text1)
        return EXIT_OK

    if cmd == "describe":
        info = commands.describe_part(args.name, root=root, hooks=hooks)

        def _text2(i):
            print(f"{i.name}: {i.description or '(no description)'}")
            print(f"  source:   {i.source}")
            if i.path:
                print(f"  path:     {i.path}")
            if i.defaults:
                import yaml

                print("  defaults:")
                for line in yaml.safe_dump(i.defaults, sort_keys=False).splitlines():
                    print(f"    {line}")

        _emit(info, as_json, _text2)
        if args.source and info.path:
            print()
            print(Path(info.path).read_text(encoding="utf-8"))
        return EXIT_OK

    if cmd == "inspect":
        reports = commands.inspect_mesh(args.mesh)
        _emit(reports, as_json, lambda rs: print("\n\n".join(r.format_text() for r in rs)))
        return EXIT_OK

    if cmd == "renders":
        bundles = commands.list_renders(root=root, limit=args.limit, hooks=hooks)

        def _text3(items):
            if not items:
                print("No render bundles found.")
            for b in items:
                print(f"{b.stem:48s} {b.created or '':20s} {len(b.files)} files{'  [png]' if b.preview else ''}")

        _emit(bundles, as_json, _text3)
        return EXIT_OK

    if cmd == "show":
        info = commands.describe_render(args.bundle, root=root, hooks=hooks)

        def _text4(b):
            print(f"{b.stem}  ({b.bundle_dir})")
            print(f"  run name: {b.run_name}   created: {b.created}")
            print("  files:    " + ", ".join(b.files))
            if b.stats:
                for k in ("render.total.duration_s", "git.branch", "git.commit"):
                    if k in b.stats:
                        print(f"  {k}: {b.stats[k]}")
            if b.log_tail:
                print("  log tail:")
                for line in b.log_tail.splitlines()[-10:]:
                    print(f"    {line}")

        _emit(info, as_json, _text4)
        return EXIT_OK

    if cmd == "project":
        info = commands.project_info(root=root, hooks=hooks)
        if as_json:
            print(json.dumps(info, indent=2, default=str))
        else:
            print(f"root: {info['root']}")
            if info["layout"]:
                for k, v in info["layout"].items():
                    print(f"  {k}: {v}")
            print("sources: " + ", ".join(info["sources"]))
        return EXIT_OK

    handler = getattr(args, "handler", None)
    if handler is not None:
        return int(handler(args, hooks) or EXIT_OK)
    return EXIT_USAGE


_VALUE_OPTIONS = {"-c", "--config", "--name", "--out", "--only", "--skip", "--root", "--limit", "--dir",
                  "--description", "--format", "--template", "--param", "--to", "--only", "--host", "--port",
                  "--transport", "--render-timeout"}
_DOTLIST_COMMANDS = {"render", "config", "upload"}


def hoist_dotlist(argv: List[str]) -> List[str]:
    """Move ``KEY=VALUE`` tokens next to the positionals so they may appear after flags
    (argparse cannot intermix positionals and optionals with sub-parsers)."""
    if not argv:
        return argv
    try:
        cmd_idx = next(i for i, a in enumerate(argv) if not a.startswith("-"))
    except StopIteration:
        return argv
    if argv[cmd_idx] not in _DOTLIST_COMMANDS:
        return argv
    head, rest = argv[: cmd_idx + 1], argv[cmd_idx + 1 :]
    positionals: List[str] = []
    others: List[str] = []
    expect_value = False
    for tok in rest:
        if expect_value:
            others.append(tok)
            expect_value = False
        elif tok.startswith("-"):
            others.append(tok)
            expect_value = tok in _VALUE_OPTIONS
        else:
            positionals.append(tok)  # target or KEY=VALUE, wherever it appears
    return head + positionals + others


def main(argv: Optional[Sequence[str]] = None, *, hooks: Optional[Hooks] = None) -> int:
    hooks = hooks or Hooks()
    parser = build_parser(hooks=hooks)
    raw = list(argv) if argv is not None else sys.argv[1:]
    args = parser.parse_args(hoist_dotlist(raw))
    if not args.command:
        parser.print_help()
        return EXIT_USAGE
    verbose = getattr(args, "verbose", False)
    _init_logging(verbose)
    try:
        return _dispatch(args, hooks)
    except CommandError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    except Exception as exc:  # noqa: BLE001
        if verbose:
            raise
        print(f"error: {type(exc).__name__}: {exc} (use -v for a traceback)", file=sys.stderr)
        return EXIT_FAILURE
