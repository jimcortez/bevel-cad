# Security policy

## Reporting a vulnerability

Please do not open a public issue for security problems.

Preferred: open a private report through GitHub Security Advisories at
<https://github.com/jimcortez/bevel-cad/security/advisories/new>.

Fallback: email <jim@jimcortez.com> with "bevel-cad security" in the subject.

You should hear back within a week. Only the latest release is actively supported.

## Scope notes

- `bevel` executes the Python part files it is pointed at (`src/<part>.py`, `pkg.module:fn`).
  Treat part files and project configs from untrusted sources like any other untrusted code.
- `bevel mcp` exposes those same capabilities to whatever MCP client connects to it. The
  `streamable-http` transport binds a local HTTP server; run it only on trusted networks.
- `bevel render --viewer` and `bevel upload` push geometry to a cadquery-web-viewer instance
  over plain HTTP at the configured `viewer.host` / `viewer.port`.
