"""``bevel skills list|install``."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from bevel_cad import scaffold
from bevel_cad.commands import CommandError
from bevel_cad.config.paths import find_project_root


def run_skills(args: argparse.Namespace, hooks: Any) -> int:
    if args.action == "list":
        items = scaffold.list_skills()
        if args.json:
            print(json.dumps([s.to_dict() for s in items], indent=2))
        else:
            for s in items:
                print(f"{s.name:28s} {s.description}")
        return 0
    if args.action == "path":
        print(scaffold.SKILLS_DIR)
        return 0
    # install
    if args.to:
        dest = Path(args.to)
    elif args.user:
        dest = Path.home() / ".claude" / "skills"
    else:
        root = Path(args.root) if args.root else find_project_root()
        if root is None:
            raise CommandError("Not inside a bevel project; pass --project from a project, --user, or --to DIR")
        dest = root / ".claude" / "skills"
    try:
        written = scaffold.install_skills(dest, force=args.force, names=args.only or ())
    except scaffold.ScaffoldError as exc:
        raise CommandError(str(exc)) from exc
    if args.json:
        print(json.dumps({"dest": str(dest), "files": written}, indent=2))
    else:
        print(f"Installed {len(written)} skill(s) into {dest}")
        for w in written:
            print(f"  {w}")
    return 0


def register(sub: argparse._SubParsersAction, add_common) -> None:
    p = sub.add_parser("skills", help="list or install the bundled agent skills")
    p.add_argument("action", choices=["list", "install", "path"])
    g = p.add_mutually_exclusive_group()
    g.add_argument("--project", action="store_true", help="install into <project>/.claude/skills (default)")
    g.add_argument("--user", action="store_true", help="install into ~/.claude/skills")
    g.add_argument("--to", metavar="DIR", help="install into DIR")
    p.add_argument("--only", action="append", metavar="NAME", help="install only this skill (repeatable)")
    p.add_argument("--force", action="store_true", help="overwrite existing skill folders")
    add_common(p)
    p.set_defaults(handler=run_skills)
