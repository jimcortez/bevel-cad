"""Collect render-run statistics and write space-aligned CSV."""

from __future__ import annotations

import logging
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, List, Mapping, Optional, Tuple

logger = logging.getLogger(__name__)

_STAGE_DESCRIPTIONS: dict[str, str] = {}

_EXPORT_LABELS = {
    "stl": "Exporting STL",
    "step": "Exporting STEP",
    "3mf": "Exporting 3MF",
    "glb": "Exporting GLB",
    "gltf": "Exporting GLTF",
    "obj": "Exporting OBJ",
    "preview": "Rendering preview",
    "config": "Writing config snapshot",
    "stats": "Writing render stats",
}

JOB_STAGE_PREFIX = "render.job."


def register_stage_descriptions(descriptions: Mapping[str, str]) -> None:
    """Register human-readable labels for custom pipeline stages (e.g. ``draw_part.sweep``)."""
    _STAGE_DESCRIPTIONS.update({str(k): str(v) for k, v in descriptions.items()})


def describe_stage(name: str) -> str:
    """Return a human-readable description for a render pipeline stage."""
    if name in _STAGE_DESCRIPTIONS:
        return _STAGE_DESCRIPTIONS[name]
    if name.startswith(JOB_STAGE_PREFIX):
        rest = name[len(JOB_STAGE_PREFIX):]
        fmt, _, filename = rest.partition(".")
        label = _EXPORT_LABELS.get(fmt, f"Running export ({fmt})")
        return f"{label} ({filename})"
    return name


@dataclass
class RenderStat:
    name: str
    value: str
    description: str


class RenderStats:
    """Namespaced stat collector passed through the render pipeline."""

    def __init__(self) -> None:
        self._stats: List[RenderStat] = []
        self._run_start = time.perf_counter()

    @property
    def stats(self) -> Tuple[RenderStat, ...]:
        return tuple(self._stats)

    def add_stat(self, name: str, value: Any, description: str) -> None:
        self._stats.append(RenderStat(name=str(name), value=str(value), description=str(description)))

    def get(self, name: str) -> Optional[str]:
        for stat in reversed(self._stats):
            if stat.name == name:
                return stat.value
        return None

    @contextmanager
    def record_stage(self, name: str) -> Iterator[None]:
        description = describe_stage(name)
        logger.info("%s", description)
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            logger.info("%s completed (%.3fs)", description, elapsed)
            self.add_stat(name, f"{elapsed:.4f}", "Stage duration in seconds")

    def populate_git_info(self, cwd: Optional[Path] = None) -> None:
        for key, cmd, desc in (
            ("git.branch", ["git", "branch", "--show-current"], "Current git branch"),
            ("git.commit", ["git", "rev-parse", "HEAD"], "Current git commit hash"),
        ):
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, check=True, timeout=5, cwd=cwd
                )
                value = result.stdout.strip()
            except (subprocess.SubprocessError, OSError):
                value = ""
            self.add_stat(key, value, desc)

    def populate_config_sources(self, sources: Iterable[Any]) -> None:
        """Record every config layer that contributed to the run.

        ``sources`` may be ``ConfigSource``-like objects (``.layer`` / ``.path``) or
        ``(layer, path)`` tuples.
        """
        for idx, src in enumerate(sources):
            if isinstance(src, tuple):
                layer, path = src
            else:
                layer, path = getattr(src, "layer", "?"), getattr(src, "path", None)
            self.add_stat(
                f"config.sources.{idx}.{layer}",
                str(path) if path else "",
                f"Config layer {idx} ({layer})",
            )

    def finalize_total_duration(self) -> None:
        total = time.perf_counter() - self._run_start
        self.add_stat("render.total.duration_s", f"{total:.4f}", "Wall-clock duration for entire render run")

    def to_rows(self) -> List[Tuple[str, str, str]]:
        return [(s.name, s.value, s.description) for s in self._stats]

    def write_csv(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = [("name", "value", "description")] + self.to_rows()
        col_widths = [max(len(row[i]) for row in rows) for i in range(3)]
        lines = [", ".join(row[i].ljust(col_widths[i]) for i in range(3)) for row in rows]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_stats_csv(path: Path) -> List[RenderStat]:
    """Parse a stats CSV written by :meth:`RenderStats.write_csv`."""
    out: List[RenderStat] = []
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    for line in lines[1:]:
        parts = [p.strip() for p in line.split(", ", 2)]
        if len(parts) == 3:
            out.append(RenderStat(*parts))
    return out
