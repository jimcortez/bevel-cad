"""
Part targets: how bevel finds and loads the code that builds geometry.

A *part* is any module (or callable) exposing ``build(cfg) -> geometry``.
The optional :func:`part` decorator attaches metadata (a name, default config
values, an optional schema).  Targets are resolved from, in order:

1. an existing ``.py`` file path,
2. ``<project>/src/<name>.py`` (or package) in the current project,
3. an importable ``package.module[:callable]``,
4. a registered name -- ``bevel_cad.parts`` / ``bevel_cad.providers`` entry
   points, and the bundled examples.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import pkgutil
import sys
from dataclasses import dataclass, field
from hashlib import sha1
from importlib.metadata import entry_points
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

PART_ATTR = "__bevel_part__"
ENTRY_POINT_GROUP = "bevel_cad.parts"
PROVIDER_GROUP = "bevel_cad.providers"
EXAMPLES_PACKAGE = "bevel_cad.examples"


class PartNotFound(LookupError):
    """No part matched the requested target."""


class InvalidPart(TypeError):
    """The target was found but does not expose a usable ``build``."""


@dataclass(frozen=True)
class PartSpec:
    """A resolved, importable part."""

    name: str
    build: Callable[[Any], Any]
    source: str
    defaults: Mapping[str, Any] = field(default_factory=dict)
    schema: Optional[type] = None
    description: str = ""
    path: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "source": self.source,
            "path": str(self.path) if self.path else None,
            "description": self.description,
            "defaults": _plain(self.defaults),
            "schema": f"{self.schema.__module__}.{self.schema.__qualname__}" if self.schema else None,
        }


@dataclass(frozen=True)
class PartRef:
    """A discoverable part that has not been imported yet."""

    name: str
    source: str
    kind: str  # project | entry-point | provider | example
    location: str
    _loader: Callable[[], PartSpec] = field(repr=False, compare=False)

    def load(self) -> PartSpec:
        return self._loader()

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "source": self.source, "kind": self.kind, "location": self.location}


def _plain(value: Any) -> Any:
    try:
        from omegaconf import DictConfig, ListConfig, OmegaConf

        if isinstance(value, (DictConfig, ListConfig)):
            return OmegaConf.to_container(value, resolve=True)
    except ImportError:  # pragma: no cover
        pass
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    return value


# --- decorator ---------------------------------------------------------------------------------


def part(
    fn: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    defaults: Optional[Mapping[str, Any]] = None,
    schema: Optional[type] = None,
    description: Optional[str] = None,
):
    """
    Mark ``build`` with metadata::

        @bevel_cad.part(defaults={"spacer": {"outer_d": 44.0}})
        def build(cfg):
            return make_spacer(cfg.spacer.outer_d)

    ``defaults`` are merged as the "part" config layer (below ``--config`` files and
    CLI overrides). ``schema`` is an optional dataclass extending ``BevelSchema``.
    """

    def deco(f: Callable) -> Callable:
        setattr(
            f,
            PART_ATTR,
            {"name": name, "defaults": dict(defaults or {}), "schema": schema, "description": description},
        )
        return f

    return deco(fn) if fn is not None else deco


# --- spec construction -------------------------------------------------------------------------


def spec_from_callable(fn: Callable, *, name: str, source: str, path: Optional[Path] = None, doc: str = "") -> PartSpec:
    if not callable(fn):
        raise InvalidPart(f"{source}: build is not callable")
    meta = getattr(fn, PART_ATTR, None) or {}
    description = meta.get("description") or doc or (inspect.getdoc(fn) or "")
    return PartSpec(
        name=meta.get("name") or name,
        build=fn,
        source=source,
        defaults=meta.get("defaults") or {},
        schema=meta.get("schema"),
        description=description.strip().splitlines()[0] if description else "",
        path=path,
    )


def spec_from_module(module: ModuleType, *, name: str, source: str, attr: str = "build") -> PartSpec:
    fn = getattr(module, attr, None)
    if fn is None:
        public = sorted(a for a in dir(module) if not a.startswith("_"))
        raise InvalidPart(f"{source}: module {module.__name__} has no {attr}(cfg) function (has: {', '.join(public)})")
    path = Path(module.__file__) if getattr(module, "__file__", None) else None
    return spec_from_callable(fn, name=name, source=source, path=path, doc=(module.__doc__ or ""))


def load_module_from_file(path: Path) -> ModuleType:
    """Import a standalone ``.py`` file; its directory is added to ``sys.path`` for sibling imports."""
    path = Path(path).resolve()
    if not path.is_file():
        raise PartNotFound(f"Part file not found: {path}")
    digest = sha1(str(path).encode()).hexdigest()[:8]
    mod_name = f"bevel_part_{path.stem}_{digest}"
    parent = str(path.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise PartNotFound(f"Cannot import part file: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(mod_name, None)
        raise
    return module


def spec_from_file(path: Path, *, name: Optional[str] = None, source_prefix: str = "file") -> PartSpec:
    path = Path(path).resolve()
    module = load_module_from_file(path)
    return spec_from_module(module, name=name or path.stem, source=f"{source_prefix}:{path}")


def spec_from_import_path(target: str, *, name: Optional[str] = None, source_prefix: str = "module") -> PartSpec:
    """``pkg.module`` or ``pkg.module:callable``."""
    mod_path, _, attr = target.partition(":")
    module = importlib.import_module(mod_path)
    part_name = name or (attr if attr and attr != "build" else mod_path.rsplit(".", 1)[-1])
    if attr:
        fn = getattr(module, attr, None)
        if fn is None:
            raise InvalidPart(f"{target}: module has no attribute {attr!r}")
        if isinstance(fn, ModuleType):
            return spec_from_module(fn, name=part_name, source=f"{source_prefix}:{target}")
        return spec_from_callable(
            fn, name=part_name, source=f"{source_prefix}:{target}",
            path=Path(module.__file__) if getattr(module, "__file__", None) else None,
        )
    return spec_from_module(module, name=part_name, source=f"{source_prefix}:{target}")


# --- discovery ---------------------------------------------------------------------------------


def _example_refs() -> List[PartRef]:
    refs: List[PartRef] = []
    try:
        pkg = importlib.import_module(EXAMPLES_PACKAGE)
    except ImportError:  # pragma: no cover
        return refs
    for info in pkgutil.iter_modules(pkg.__path__):
        if info.name.startswith("_"):
            continue
        mod = f"{EXAMPLES_PACKAGE}.{info.name}"
        refs.append(
            PartRef(
                name=info.name, source=f"example:{mod}", kind="example", location=mod,
                _loader=lambda mod=mod, n=info.name: spec_from_import_path(mod, name=n, source_prefix="example"),
            )
        )
    return refs


def _entry_point_refs() -> List[PartRef]:
    refs: List[PartRef] = []
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        if ep.value.startswith(EXAMPLES_PACKAGE + "."):
            continue  # bundled examples are listed by _example_refs
        refs.append(
            PartRef(
                name=ep.name, source=f"entry-point:{ep.name}", kind="entry-point", location=ep.value,
                _loader=lambda ep=ep: _spec_from_entry_value(ep.value, name=ep.name, source=f"entry-point:{ep.name}"),
            )
        )
    return refs


def _spec_from_entry_value(value: Any, *, name: str, source: str) -> PartSpec:
    if isinstance(value, ModuleType):
        return spec_from_module(value, name=name, source=source)
    if callable(value):
        return spec_from_callable(value, name=name, source=source)
    return spec_from_import_path(str(value), name=name, source_prefix=source.split(":", 1)[0])


def _provider_refs() -> List[PartRef]:
    refs: List[PartRef] = []
    for ep in entry_points(group=PROVIDER_GROUP):
        try:
            mapping = ep.load()()
        except Exception as exc:  # noqa: BLE001 - a broken provider must not hide the others
            import logging

            logging.getLogger(__name__).warning("bevel provider %s failed: %s", ep.name, exc)
            continue
        for pname, value in dict(mapping).items():
            src = f"provider:{ep.name}:{pname}"
            refs.append(
                PartRef(
                    name=str(pname), source=src, kind="provider",
                    location=value if isinstance(value, str) else getattr(value, "__name__", repr(value)),
                    _loader=lambda v=value, n=str(pname), s=src: _spec_from_entry_value(v, name=n, source=s),
                )
            )
    return refs


def _project_refs(layout: Any) -> List[PartRef]:
    refs: List[PartRef] = []
    if layout is None:
        return refs
    for name in layout.iter_source_names():
        path = layout.source_file_for(name)
        if path is None:
            continue
        refs.append(
            PartRef(
                name=name, source=f"file:{path}", kind="project", location=str(path),
                _loader=lambda p=path, n=name: spec_from_file(p, name=n),
            )
        )
    return refs


def iter_registered_parts(layout: Any = None) -> List[PartRef]:
    """All discoverable parts, project first; later duplicates of a name are dropped."""
    seen: Dict[str, PartRef] = {}
    for ref in (*_project_refs(layout), *_entry_point_refs(), *_provider_refs(), *_example_refs()):
        seen.setdefault(ref.name, ref)
    return sorted(seen.values(), key=lambda r: (r.kind != "project", r.name))


def find_registered(name: str, layout: Any = None) -> Optional[PartRef]:
    for ref in iter_registered_parts(layout):
        if ref.name == name:
            return ref
    return None


# --- resolution --------------------------------------------------------------------------------


def _looks_like_import_path(target: str) -> bool:
    head = target.split(":", 1)[0]
    return all(p.isidentifier() for p in head.split(".")) and "." in head or ":" in target


def load_target(target: str, *, layout: Any = None) -> PartSpec:
    """Resolve ``target`` (file, project name, import path, or registered name) to a :class:`PartSpec`."""
    target = str(target).strip()
    if not target:
        raise PartNotFound("empty part target")

    p = Path(target).expanduser()
    if p.suffix == ".py" and p.is_file():
        return spec_from_file(p)
    if p.is_dir() and (p / "__init__.py").is_file():
        return spec_from_file(p / "__init__.py", name=p.name)

    if layout is not None and "/" not in target and ":" not in target:
        src = layout.source_file_for(target)
        if src is not None:
            return spec_from_file(src, name=target)

    ref = find_registered(target, layout)
    if ref is not None:
        return ref.load()

    if _looks_like_import_path(target) or target.isidentifier():
        try:
            return spec_from_import_path(target)
        except ModuleNotFoundError as exc:
            if exc.name and target.split(":", 1)[0].startswith(exc.name):
                pass  # the target itself is missing; fall through to the not-found error
            else:
                raise

    available = ", ".join(r.name for r in iter_registered_parts(layout)) or "<none>"
    raise PartNotFound(f"Unknown part target {target!r}. Available parts: {available}")


def run_build(spec: PartSpec, cfg: Any) -> Any:
    """Call ``build(cfg)`` and return the geometry (``None`` means the part rendered itself)."""
    return spec.build(cfg)
