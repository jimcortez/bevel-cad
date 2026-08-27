"""Project-root discovery and the normalized project layout."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence, Tuple, Union

PROJECT_FILE = "bevel.yaml"
LOCAL_FILE = "bevel.local.yaml"
ENV_ROOT = "BEVEL_ROOT"


def find_project_root(start: Optional[Union[str, Path]] = None) -> Optional[Path]:
    """
    Locate the nearest directory containing ``bevel.yaml`` walking up from ``start``
    (default cwd). ``$BEVEL_ROOT`` overrides the search when set.
    """
    env = os.environ.get(ENV_ROOT)
    if env:
        return Path(env).expanduser().resolve()
    here = Path(start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / PROJECT_FILE).is_file():
            return candidate
    return None


def user_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "bevel" / "config.yaml"


def _as_list(value: Any) -> Tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, Path)):
        return (str(value),)
    return tuple(str(v) for v in value)


@dataclass(frozen=True)
class ProjectLayout:
    """Absolute paths for a project's config / source / render directories."""

    root: Path
    configs_dirs: Tuple[Path, ...]
    src_dir: Path
    renders_dir: Path

    @classmethod
    def from_config(cls, root: Union[str, Path], cfg: Any) -> "ProjectLayout":
        root = Path(root).resolve()
        project = getattr(cfg, "project", None)
        configs = _as_list(getattr(project, "configs_dir", "configs")) or ("configs",)
        src = str(getattr(project, "src_dir", "src") or "src")
        out = str(getattr(getattr(cfg, "rendering", None), "output_dir", "renders") or "renders")
        return cls(
            root=root,
            configs_dirs=tuple(_resolve(root, c) for c in configs),
            src_dir=_resolve(root, src),
            renders_dir=_resolve(root, out),
        )

    def config_file_for(self, name: str) -> Optional[Path]:
        for d in self.configs_dirs:
            for ext in (".yaml", ".yml"):
                p = d / f"{name}{ext}"
                if p.is_file():
                    return p
        return None

    def source_file_for(self, name: str) -> Optional[Path]:
        p = self.src_dir / f"{name}.py"
        if p.is_file():
            return p
        pkg = self.src_dir / name / "__init__.py"
        if pkg.is_file():
            return pkg
        return None

    def iter_source_names(self) -> Sequence[str]:
        if not self.src_dir.is_dir():
            return ()
        names = []
        for p in sorted(self.src_dir.iterdir()):
            if p.name.startswith(("_", ".")):
                continue
            if p.suffix == ".py":
                names.append(p.stem)
            elif p.is_dir() and (p / "__init__.py").is_file():
                names.append(p.name)
        return tuple(names)


def _resolve(base: Path, value: Union[str, Path]) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else (base / p)


def resolve_output_dir(cfg: Any, root: Optional[Path]) -> Path:
    """``rendering.output_dir`` relative to the project root (or cwd without a project)."""
    out = str(getattr(getattr(cfg, "rendering", None), "output_dir", "renders") or "renders")
    return _resolve(root or Path.cwd(), out).resolve()
