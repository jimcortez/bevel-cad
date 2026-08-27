"""``bevel mcp``: run the MCP server."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from bevel_cad.commands import CommandError


def run_mcp(args: argparse.Namespace, hooks: Any) -> int:
    try:
        from bevel_cad.mcp import create_server
    except ImportError as exc:  # pragma: no cover
        raise CommandError("the MCP SDK is not installed; pip install 'bevel-cad[mcp]'") from exc
    root = Path(args.root).resolve() if args.root else None
    # stdio transport uses stdout for the protocol; keep logging on stderr and quiet.
    logging.getLogger().setLevel(logging.DEBUG if args.verbose else logging.WARNING)
    server = create_server(root=root, hooks=hooks, render_timeout=args.render_timeout)
    if args.transport == "stdio":
        server.run("stdio")
    else:
        server.run("streamable-http", host=args.host, port=args.port)
    return 0


def register(sub: argparse._SubParsersAction, add_common) -> None:
    p = sub.add_parser("mcp", help="run the MCP server exposing every bevel command to AI agents")
    p.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--render-timeout", type=float, default=1800.0, help="seconds before a render subprocess is killed")
    add_common(p)
    p.set_defaults(handler=run_mcp)
