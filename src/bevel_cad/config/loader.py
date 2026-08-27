"""
Layered configuration loading on top of OmegaConf.

Layer order (lowest to highest precedence)::

    built-in defaults -> user config -> project bevel.yaml -> bevel.local.yaml
      -> part defaults -> --config files -> CLI dotlist -> programmatic overrides

Rules:
* the merged config is **struct** (unknown attribute access raises); use
  ``cfg.get("key", default)`` for optional free-form keys;
* the ``project`` / ``rendering`` / ``viewer`` blocks are typed and validated;
  every other top-level key is free-form;
* legacy led_knots-style layers (``server:`` block, list-form
  ``rendering.exports``) are normalised transparently.
"""

from __future__ import annotations

import logging
import os
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

import yaml
from omegaconf import DictConfig, ListConfig, OmegaConf

from bevel_cad.render.naming import DEFAULT_FILENAME_TEMPLATES, VALID_EXPORT_FORMATS, slugify

from .paths import LOCAL_FILE, PROJECT_FILE, ProjectLayout, find_project_root, user_config_path
from .schema import BevelSchema

logger = logging.getLogger(__name__)

DEFAULTS_PATH = Path(__file__).with_name("defaults.yaml")

_VIEWER_ENV_MAP = {
    "protocol": "CADQUERY_WEB_VIEWER_PROTOCOL",
    "texture": "CADQUERY_WEB_VIEWER_TEXTURE",
    "color_faces": "CADQUERY_WEB_VIEWER_COLOR_FACES",
    "color_edges": "CADQUERY_WEB_VIEWER_COLOR_EDGES",
    "color_vertices": "CADQUERY_WEB_VIEWER_COLOR_VERTICES",
}

# Keys from the pre-bevel export schema that no longer mean anything.
_DROPPED_EXPORT_KEYS = ("stl_cache", "dpi", "mesh_tolerance", "mesh_angular_tolerance")


class ConfigError(ValueError):
    """Raised for invalid or unloadable configuration."""


@dataclass(frozen=True)
class ConfigSource:
    layer: str  # defaults | user | project | local | part | file | dotlist | override
    path: Optional[Path] = None

    def __str__(self) -> str:
        return f"{self.layer}:{self.path}" if self.path else self.layer


@dataclass
class LoadedConfig:
    cfg: DictConfig
    sources: tuple
    root: Optional[Path]
    layout: Optional[ProjectLayout]


# --- legacy normalisation -----------------------------------------------------------------


def _exports_list_to_dict(entries: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for entry in entries:
        job = dict(entry or {})
        fmt = str(job.get("format", "")).strip().lower()
        if fmt not in VALID_EXPORT_FORMATS:
            raise ConfigError(f"rendering.exports entry has unknown format {fmt!r}")
        filename = job.get("filename") or DEFAULT_FILENAME_TEMPLATES[fmt]
        key = fmt if filename == DEFAULT_FILENAME_TEMPLATES[fmt] else slugify(str(filename)) or fmt
        if key in out:
            raise ConfigError(f"rendering.exports has two entries resolving to job {key!r}")
        job.pop("format", None)
        if filename == DEFAULT_FILENAME_TEMPLATES[fmt]:
            job.pop("filename", None)
        if key != fmt:
            job["format"] = fmt
        out[key] = job
    return out


def normalize_layer(data: Any, *, source: str = "<config>") -> Dict[str, Any]:
    """Convert legacy shapes to the current schema. Returns a new plain dict."""
    if data is None:
        return {}
    if not isinstance(data, Mapping):
        raise ConfigError(f"{source}: top level must be a mapping, got {type(data).__name__}")
    out: Dict[str, Any] = dict(data)

    # server: {protocol, texture, color_*, viewer: {...}}  ->  viewer: {...}
    server = out.pop("server", None)
    if isinstance(server, Mapping):
        viewer: Dict[str, Any] = dict(out.get("viewer") or {})
        style: Dict[str, Any] = dict(viewer.get("style") or {})
        for k in ("protocol", "texture", "color_faces", "color_edges", "color_vertices"):
            if k in server:
                style[k] = server[k]
        sv = server.get("viewer") or {}
        remote = sv.get("remote") or {}
        for k in ("host", "port", "upload_timeout", "post_timeout"):
            if k in sv:
                viewer[k] = sv[k]
            elif k in remote:
                viewer[k] = remote[k]
        if "tessellation_tolerance" in sv:
            viewer["tolerance"] = sv["tessellation_tolerance"]
        if "tessellation_angular_tolerance" in sv:
            viewer["angular_tolerance"] = sv["tessellation_angular_tolerance"]
        if style:
            viewer["style"] = style
        out["viewer"] = viewer
        warnings.warn(f"{source}: 'server:' block is deprecated; use 'viewer:'", DeprecationWarning, stacklevel=3)

    rendering = out.get("rendering")
    if isinstance(rendering, Mapping):
        rendering = dict(rendering)
        exports = rendering.get("exports")
        if isinstance(exports, (list, tuple, ListConfig)):
            rendering["exports"] = _exports_list_to_dict(list(exports))
            warnings.warn(
                f"{source}: list-form rendering.exports is deprecated; use a mapping keyed by job name",
                DeprecationWarning,
                stacklevel=3,
            )
        exports = rendering.get("exports")
        if isinstance(exports, Mapping):
            cleaned: Dict[str, Any] = {}
            for key, job in exports.items():
                job = dict(job or {})
                for dk in _DROPPED_EXPORT_KEYS:
                    if dk in job:
                        job.pop(dk)
                        logger.debug("%s: ignoring obsolete export key %s.%s", source, key, dk)
                cleaned[str(key)] = job
            rendering["exports"] = cleaned
        out["rendering"] = rendering
    return out


# --- loading --------------------------------------------------------------------------------


def _read_yaml(path: Path) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except FileNotFoundError:
        raise ConfigError(f"Config file not found: {path}") from None
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc
    return normalize_layer(data, source=str(path))


def _coerce_layer(data: Any, *, source: str) -> DictConfig:
    if isinstance(data, DictConfig):
        data = OmegaConf.to_container(data, resolve=False)
    return OmegaConf.create(normalize_layer(data, source=source))


def apply_viewer_env(cfg: DictConfig) -> None:
    """Export ``viewer.style.*`` as ``CADQUERY_WEB_VIEWER_*`` (read by the viewer at import)."""
    style = OmegaConf.select(cfg, "viewer.style")
    if style is None:
        return
    for attr, env_name in _VIEWER_ENV_MAP.items():
        val = style.get(attr)
        if val is not None:
            os.environ[env_name] = str(val)


def load_layers(
    *,
    files: Sequence[Union[str, Path]] = (),
    dotlist: Sequence[str] = (),
    overrides: Optional[Union[Mapping[str, Any], DictConfig]] = None,
    schema: Optional[type] = None,
    part_defaults: Optional[Mapping[str, Any]] = None,
    project_config: Union[str, Path, None] = "auto",
    user_config: bool = True,
    apply_viewer_env_vars: bool = True,
    root: Optional[Union[str, Path]] = None,
) -> LoadedConfig:
    """
    Merge every configuration layer and return the struct ``DictConfig`` plus provenance.

    ``project_config="auto"`` discovers ``bevel.yaml`` by walking up from ``root``/cwd;
    pass an explicit path (any name) or ``None`` to disable.
    """
    layers: List[DictConfig] = []
    sources: List[ConfigSource] = []

    def add(data: Any, layer: str, path: Optional[Path] = None) -> None:
        layers.append(_coerce_layer(data, source=str(path or layer)))
        sources.append(ConfigSource(layer, path))

    add(_read_yaml(DEFAULTS_PATH), "defaults", DEFAULTS_PATH)

    if user_config:
        up = user_config_path()
        if up.is_file():
            add(_read_yaml(up), "user", up)

    resolved_root: Optional[Path] = Path(root).resolve() if root else None
    project_path: Optional[Path] = None
    if project_config == "auto":
        resolved_root = resolved_root or find_project_root()
        if resolved_root and (resolved_root / PROJECT_FILE).is_file():
            project_path = resolved_root / PROJECT_FILE
    elif project_config is not None:
        project_path = Path(project_config).resolve()
        resolved_root = resolved_root or project_path.parent
    if project_path is not None:
        add(_read_yaml(project_path), "project", project_path)
        local_path = project_path.with_name(LOCAL_FILE)
        if not local_path.is_file() and project_path.name != PROJECT_FILE:
            # led_knots-style: config.yaml + config.local.yaml
            alt = project_path.with_name(f"{project_path.stem}.local{project_path.suffix}")
            local_path = alt if alt.is_file() else local_path
        if local_path.is_file():
            add(_read_yaml(local_path), "local", local_path)

    if part_defaults:
        add(dict(part_defaults), "part")

    for f in files:
        fp = Path(f).expanduser()
        if not fp.is_absolute():
            fp = Path.cwd() / fp
        add(_read_yaml(fp), "file", fp.resolve())

    if dotlist:
        layers.append(OmegaConf.from_dotlist([str(d) for d in dotlist]))
        sources.append(ConfigSource("dotlist"))

    if overrides:
        add(overrides, "override")

    base = OmegaConf.structured(schema or BevelSchema)
    OmegaConf.set_struct(base, False)
    try:
        cfg = OmegaConf.merge(base, *layers)
    except Exception as exc:  # omegaconf raises many ValidationError subclasses
        raise ConfigError(f"Configuration error: {exc}") from exc
    OmegaConf.set_struct(cfg, True)

    if apply_viewer_env_vars:
        apply_viewer_env(cfg)

    layout = ProjectLayout.from_config(resolved_root, cfg) if resolved_root else None
    return LoadedConfig(cfg=cfg, sources=tuple(sources), root=resolved_root, layout=layout)


def load_config(**kwargs: Any) -> DictConfig:
    """Shorthand for ``load_layers(**kwargs).cfg``."""
    return load_layers(**kwargs).cfg


def config_to_yaml(cfg: DictConfig, *, resolve: bool = True) -> str:
    """Serialise a config (interpolations resolved) for the bundle snapshot."""
    return OmegaConf.to_yaml(cfg, resolve=resolve, sort_keys=False)


def config_to_dict(cfg: Any) -> Any:
    """Plain python container (``DictConfig`` -> dict, ``ListConfig`` -> list)."""
    if isinstance(cfg, (DictConfig, ListConfig)):
        return OmegaConf.to_container(cfg, resolve=True)
    return cfg
