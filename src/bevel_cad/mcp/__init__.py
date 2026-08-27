"""MCP server exposing bevel commands to AI agents (``bevel mcp``)."""

from .server import create_server

__all__ = ["create_server"]
