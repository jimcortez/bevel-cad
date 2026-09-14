"""``bevel create`` and ``bevel add``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from bevel_cad import scaffold
from bevel_cad.commands import CommandError
from bevel_cad.scaffold import PRIMARY_FORMATS, ScaffoldError


def _prompt(label: str, default: Optional[str] = None, *, choices: Sequence[str] = (), yes: bool = False) -> str:
    if yes:
        if default is None:
            raise CommandError(f"--yes given but no default for {label!r}")
        return default
    if not sys.stdin.isatty():
        if default is not None:
            return default
        raise CommandError(f"{label} is required (non-interactive session; pass it on the command line)")
    hint = f" [{'/'.join(choices)}]" if choices else ""
    dflt = f" ({default})" if default not in (None, "") else ""
    while True:
        raw = input(f"{label}{hint}{dflt}: ").strip()
        if not raw and default is not None:
            return default
        if raw and (not choices or raw in choices):
            return raw
        print("  please enter a value" + (f" from {', '.join(choices)}" if choices else ""))


def _parse_params(items: Sequence[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for item in items or ():
        if "=" not in item:
            raise CommandError(f"--param expects KEY=VALUE, got {item!r}")
        k, v = item.split("=", 1)
        out[k.strip()] = v
    return out


def _collect_prompts(template: str, given: Dict[str, str], *, yes: bool) -> Dict[str, str]:
    tinfo = scaffold.get_template(template)
    values = dict(given)
    for p in tinfo.prompts:
        if p.key not in values:
            values[p.key] = _prompt(p.prompt, p.default, yes=yes)
    return values


def _emit(res: scaffold.ScaffoldResult, as_json: bool) -> None:
    if as_json:
        print(json.dumps(res.to_dict(), indent=2))
        return
    print(f"Created {len(res.files)} file(s) under {res.root}")
    for f in res.files:
        print(f"  {Path(f).relative_to(res.root) if f.startswith(res.root) else f}")
    if res.next_steps:
        print("Next:")
        for step in res.next_steps:
            print(f"  {step}")


def run_create(args: argparse.Namespace, hooks: Any) -> int:
    yes = bool(args.yes)
    templates = [t.name for t in scaffold.list_templates()] + ["none"]
    try:
        name = args.name or _prompt("Project name", yes=yes)
        description = args.description if args.description is not None else _prompt("Description", "", yes=yes)
        fmt = args.format or _prompt("Default output model type", "stl", choices=PRIMARY_FORMATS, yes=yes)
        template = args.template or _prompt("Starting template", "basic", choices=templates, yes=yes)
        params = _collect_prompts(template, _parse_params(args.param), yes=yes) if template != "none" else {}
        res = scaffold.create_project(
            name, description=description, format=fmt, template=template,
            directory=Path(args.dir) if args.dir else None, params=params,
            with_skills=not args.no_skills, force=args.force,
        )
    except ScaffoldError as exc:
        raise CommandError(str(exc)) from exc
    _emit(res, args.json)
    return 0


def run_add(args: argparse.Namespace, hooks: Any) -> int:
    yes = bool(args.yes)
    templates = [t.name for t in scaffold.list_templates()]
    try:
        name = args.name or _prompt("Part name", yes=yes)
        template = args.template or _prompt("Template", "basic", choices=templates, yes=yes)
        params = _collect_prompts(template, _parse_params(args.param), yes=yes)
        res = scaffold.add_part(
            name, template=template, description=args.description or "",
            root=Path(args.root) if args.root else None, params=params, force=args.force,
        )
    except ScaffoldError as exc:
        raise CommandError(str(exc)) from exc
    _emit(res, args.json)
    return 0


def run_templates(args: argparse.Namespace, hooks: Any) -> int:
    items = scaffold.list_templates()
    if args.json:
        print(json.dumps([t.to_dict() for t in items], indent=2))
    else:
        for t in items:
            extra = f"  (asks: {', '.join(p.key for p in t.prompts)})" if t.prompts else ""
            print(f"{t.name:10s} {t.description}{extra}")
    return 0


def register(sub: argparse._SubParsersAction, add_common) -> None:
    p = sub.add_parser("create", help="scaffold a new bevel project (interactive when arguments are omitted)")
    p.add_argument("name", nargs="?", help="project name (also the directory and the first part's name)")
    p.add_argument("--description")
    p.add_argument("--format", choices=PRIMARY_FORMATS, help="default output model type")
    p.add_argument("--template", help="starting template (see `bevel templates`), or 'none' for an empty project")
    p.add_argument("--dir", help="create the project here instead of ./<name>")
    p.add_argument("--param", action="append", default=[], metavar="KEY=VALUE", help="template prompt value, e.g. text=Hello")
    p.add_argument("-y", "--yes", action="store_true", help="accept defaults, never prompt")
    p.add_argument("--no-skills", action="store_true", help="do not copy the bevel skills into .claude/skills")
    p.add_argument("--force", action="store_true", help="overwrite existing files")
    add_common(p)
    p.set_defaults(handler=run_create)

    p = sub.add_parser("add", help="add a part (src/<name>.py + configs/<name>.yaml) to the current project")
    p.add_argument("name", nargs="?")
    p.add_argument("--template")
    p.add_argument("--description")
    p.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
    p.add_argument("-y", "--yes", action="store_true")
    p.add_argument("--force", action="store_true")
    add_common(p)
    p.set_defaults(handler=run_add)

    p = sub.add_parser("templates", help="list starting templates")
    add_common(p)
    p.set_defaults(handler=run_templates)
