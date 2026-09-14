"""
The command layer shared by the ``bevel`` CLI and the MCP server.

Every function here is plain Python with typed arguments and a result object
that has ``to_dict()``; the CLI prints it, the MCP server returns it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Union

from omegaconf import DictConfig, OmegaConf, open_dict

from bevel_cad.config import LoadedConfig, config_to_yaml, load_layers
from bevel_cad.config.paths import ProjectLayout
from bevel_cad.mesh.inspect import MeshReport, inspect_mesh_file
from bevel_cad.parts import PartSpec, iter_registered_parts, load_target
from bevel_cad.render.bundle import RenderBundle, resolve_render_bundle
from bevel_cad.render.logbuffer import discard_render_log_buffer
from bevel_cad.render.naming import VALID_EXPORT_FORMATS
from bevel_cad.render.pipeline import RenderResult, consume_last_result, render_part, start_run
from bevel_cad.render.planner import RenderPlanner
from bevel_cad.render.stats import read_stats_csv

logger = logging.getLogger(__name__)

PathLike = Union[str, Path]


@dataclass
class Hooks:
    """Extension points for projects that wrap bevel (e.g. led_knots)."""

    schema: Optional[type] = None
    project_config: Union[str, Path, None] = "auto"
    resolve_target: Optional[Callable[[DictConfig, Optional[ProjectLayout]], Optional[PartSpec]]] = None
    prepare_config: Optional[Callable[[DictConfig, LoadedConfig, Any], Any]] = None  # (cfg, loaded, run) -> build cfg
    add_render_flags: Optional[Callable[[Any], None]] = None
    stage_descriptions: Mapping[str, str] = field(default_factory=dict)


class CommandError(RuntimeError):
    """A user-facing failure (bad target, bad config, viewer down, ...)."""


# --- config resolution -------------------------------------------------------------------------


@dataclass
class ResolvedTarget:
    loaded: LoadedConfig
    spec: Optional[PartSpec]
    files: List[Path]


def _is_yaml(s: str) -> bool:
    return s.lower().endswith((".yaml", ".yml"))


def resolve_target_and_config(
    target: Optional[str] = None,
    *,
    configs: Sequence[PathLike] = (),
    overrides: Sequence[str] = (),
    root: Optional[PathLike] = None,
    hooks: Optional[Hooks] = None,
    require_part: bool = True,
) -> ResolvedTarget:
    """
    Two-pass load: layers without the part -> find the part -> re-merge with its defaults.

    ``target`` may be a ``.py``/``.yaml`` path, a project part name (``configs/<name>.yaml``
    and/or ``src/<name>.py``), an import path, or a registered name.  A ``.yaml`` target (or a
    project config for the name) is appended as the last ``--config`` layer, and its ``part:``
    key names the code to run.
    """
    hooks = hooks or Hooks()
    files: List[Path] = [Path(c) for c in configs]
    dotlist = list(overrides)
    code_target: Optional[str] = None

    if target and _is_yaml(target) and Path(target).is_file():
        files.append(Path(target))
    elif target:
        code_target = target

    def _load(part_defaults=None, schema=None):
        return load_layers(
            files=files, dotlist=dotlist, schema=schema or hooks.schema, part_defaults=part_defaults,
            project_config=hooks.project_config, root=root,
        )

    lc = _load()
    layout = lc.layout

    # project config for a bare name: configs/<name>.yaml
    if code_target and layout is not None and "/" not in code_target and not code_target.endswith(".py"):
        cfg_file = layout.config_file_for(code_target)
        if cfg_file is not None and cfg_file not in files:
            files.append(cfg_file)
            lc = _load()
            layout = lc.layout
            part_key = lc.cfg.get("part")
            if part_key:
                code_target = str(part_key)  # configs/<name>.yaml may point at another source

    spec: Optional[PartSpec] = None
    if code_target is None:
        code_target = lc.cfg.get("part") or None
    if code_target is None and hooks.resolve_target is not None:
        spec = hooks.resolve_target(lc.cfg, layout)
    if spec is None and code_target is not None:
        try:
            spec = load_target(code_target, layout=layout)
        except LookupError as exc:
            raise CommandError(str(exc)) from exc
    if spec is None and require_part:
        raise CommandError("No part given: pass a target (file, name, or module) or set 'part:' in the config")

    if spec is not None and (spec.defaults or spec.schema):
        lc = _load(part_defaults=spec.defaults, schema=spec.schema)
    return ResolvedTarget(loaded=lc, spec=spec, files=files)


def apply_export_filters(cfg: DictConfig, *, only: Sequence[str] = (), skip: Sequence[str] = ()) -> None:
    """Mutate ``rendering.exports.*.enabled`` for ``--only`` / ``--skip`` (format or job names)."""
    only_set = {s.strip().lower() for s in only if s.strip()}
    skip_set = {s.strip().lower() for s in skip if s.strip()}
    for key in only_set | skip_set:
        if key not in VALID_EXPORT_FORMATS and key not in cfg.rendering.exports:
            raise CommandError(f"Unknown export format/job {key!r}; expected one of {sorted(VALID_EXPORT_FORMATS)}")
    with open_dict(cfg):
        for name, job in cfg.rendering.exports.items():
            fmt = str(job.get("format", name)).lower()
            keys = {str(name).lower(), fmt}
            if only_set and fmt not in ("config", "stats"):
                job["enabled"] = bool(keys & only_set)
            if keys & skip_set:
                job["enabled"] = False


# --- commands ---------------------------------------------------------------------------------


def render(
    target: Optional[str] = None,
    *,
    configs: Sequence[PathLike] = (),
    overrides: Sequence[str] = (),
    name: Optional[str] = None,
    out: Optional[PathLike] = None,
    only: Sequence[str] = (),
    skip: Sequence[str] = (),
    viewer: Optional[bool] = None,
    root: Optional[PathLike] = None,
    hooks: Optional[Hooks] = None,
    now: Optional[datetime] = None,
) -> RenderResult:
    """Build the part and write its render bundle. Returns a :class:`RenderResult`."""
    hooks = hooks or Hooks()
    dots = list(overrides)
    if out:
        dots.append(f"rendering.output_dir={out}")
    rt = resolve_target_and_config(target, configs=configs, overrides=dots, root=root, hooks=hooks)
    lc, spec = rt.loaded, rt.spec
    assert spec is not None
    cfg = lc.cfg
    apply_export_filters(cfg, only=only, skip=skip)
    if hooks.stage_descriptions:
        from bevel_cad.render.stats import register_stage_descriptions

        register_stage_descriptions(hooks.stage_descriptions)

    run = start_run(cfg, name=name, root=lc.root, sources=lc.sources, part_source=spec.source, part_name=spec.name, now=now)
    build_cfg: Any = hooks.prepare_config(cfg, lc, run) if hooks.prepare_config else cfg
    logger.info("Building part %s (%s)", spec.name, spec.source)
    consume_last_result()  # forget results from earlier renders in this process
    with run.stats.record_stage("build"):
        geometry = spec.build(build_cfg)
    if geometry is None:
        # Legacy contract: the part rendered itself through bevel_cad.render_part; report that bundle.
        last = consume_last_result()
        if isinstance(last, RenderResult):
            return last
        logger.info("build() returned None; assuming the part rendered itself (legacy contract)")
        discard_render_log_buffer()
        plan = RenderPlanner.from_run(run, viewer=viewer)
        return RenderResult(run=run, plan=plan, written={}, extra_paths=(), viewer_names=())
    try:
        return render_part(geometry, run, viewer=viewer)
    except Exception as exc:
        from bevel_cad.render.pipeline import ExportError
        from bevel_cad.viewer import ViewerUnavailable, ViewerUnreachable

        if isinstance(exc, (ExportError, ViewerUnavailable, ViewerUnreachable)):
            raise CommandError(str(exc)) from exc
        raise


def resolve_config(
    target: Optional[str] = None,
    *,
    configs: Sequence[PathLike] = (),
    overrides: Sequence[str] = (),
    root: Optional[PathLike] = None,
    hooks: Optional[Hooks] = None,
) -> str:
    """The fully merged config (with the part's defaults, if resolvable) as YAML."""
    rt = resolve_target_and_config(target, configs=configs, overrides=overrides, root=root, hooks=hooks, require_part=False)
    return config_to_yaml(rt.loaded.cfg)


@dataclass
class UploadResult:
    bundle_dir: str
    stem: str
    viewer_names: List[str]
    viewer_url: str

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


def upload(
    bundle: PathLike,
    *,
    configs: Sequence[PathLike] = (),
    overrides: Sequence[str] = (),
    name: Optional[str] = None,
    root: Optional[PathLike] = None,
) -> UploadResult:
    """Push an existing bundle's GLB to the viewer using the bundle's config snapshot."""
    from bevel_cad import viewer as viewer_mod

    try:
        rb: RenderBundle = resolve_render_bundle(Path(bundle))
    except (ValueError, FileNotFoundError) as exc:
        raise CommandError(str(exc)) from exc
    files: List[Path] = []
    if rb.config_yaml.is_file():
        files.append(rb.config_yaml)
    files.extend(Path(c) for c in configs)
    lc = load_layers(files=files, dotlist=list(overrides), project_config=None if rb.config_yaml.is_file() else "auto", root=root)
    try:
        names = viewer_mod.upload_bundle(rb, lc.cfg, name=name)
    except (viewer_mod.ViewerUnavailable, viewer_mod.ViewerUnreachable) as exc:
        raise CommandError(str(exc)) from exc
    return UploadResult(bundle_dir=str(rb.bundle_dir), stem=rb.stem, viewer_names=names, viewer_url=viewer_mod.viewer_url(lc.cfg))


def _layout(root: Optional[PathLike], hooks: Optional[Hooks] = None) -> Optional[ProjectLayout]:
    hooks = hooks or Hooks()
    lc = load_layers(schema=hooks.schema, project_config=hooks.project_config, root=root, apply_viewer_env_vars=False)
    return lc.layout


@dataclass
class PartInfo:
    name: str
    source: str
    kind: str
    location: str
    description: str = ""
    path: Optional[str] = None
    defaults: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


def list_parts(*, root: Optional[PathLike] = None, hooks: Optional[Hooks] = None) -> List[PartInfo]:
    """Every discoverable part without importing any of them."""
    return [PartInfo(**r.to_dict()) for r in iter_registered_parts(_layout(root, hooks))]


def describe_part(name: str, *, root: Optional[PathLike] = None, hooks: Optional[Hooks] = None) -> PartInfo:
    """Import one part and report its metadata and declared defaults."""
    layout = _layout(root, hooks)
    try:
        spec = load_target(name, layout=layout)
    except LookupError as exc:
        raise CommandError(str(exc)) from exc
    kind = spec.source.split(":", 1)[0]
    return PartInfo(
        name=spec.name, source=spec.source, kind=kind, location=str(spec.path or spec.source),
        description=spec.description, path=str(spec.path) if spec.path else None, defaults=spec.to_dict()["defaults"],
    )


def read_part_source(name: str, *, root: Optional[PathLike] = None, hooks: Optional[Hooks] = None) -> str:
    info = describe_part(name, root=root, hooks=hooks)
    if not info.path:
        raise CommandError(f"Part {name!r} has no source file")
    return Path(info.path).read_text(encoding="utf-8")


def inspect_mesh(paths: Sequence[PathLike]) -> List[MeshReport]:
    reports = []
    for p in paths:
        try:
            reports.append(inspect_mesh_file(p))
        except (FileNotFoundError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
    return reports


_STEM_RE = re.compile(r"^(?P<slug>.+)_(?P<ts>\d{8}-\d{6})$")


@dataclass
class BundleInfo:
    stem: str
    bundle_dir: str
    run_name: Optional[str]
    created: Optional[str]
    files: List[str]
    preview: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    stats: Optional[Dict[str, str]] = None
    log_tail: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


def _bundle_info(bundle_dir: Path, *, detailed: bool = False) -> BundleInfo:
    stem = bundle_dir.name
    m = _STEM_RE.match(stem)
    created = None
    if m:
        try:
            created = datetime.strptime(m.group("ts"), "%Y%m%d-%H%M%S").isoformat()
        except ValueError:
            created = None
    files = sorted(p.name for p in bundle_dir.iterdir() if p.is_file())
    preview = next((str(bundle_dir / f) for f in files if f == f"{stem}.png"), None)
    run_name: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    stats: Optional[Dict[str, str]] = None
    log_tail: Optional[str] = None
    cfg_path = bundle_dir / f"{stem}.yaml"
    if cfg_path.is_file():
        import yaml

        try:
            config = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            run_name = (config.get("rendering") or {}).get("name")
        except yaml.YAMLError:
            config = None
    if detailed:
        csv_path = bundle_dir / f"{stem}.csv"
        if csv_path.is_file():
            stats = {s.name: s.value for s in read_stats_csv(csv_path)}
        log_path = bundle_dir / f"{stem}.log"
        if log_path.is_file():
            log_tail = "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-40:])
    else:
        config = None
    return BundleInfo(stem=stem, bundle_dir=str(bundle_dir), run_name=run_name or (m.group("slug") if m else None),
                      created=created, files=files, preview=preview, config=config, stats=stats, log_tail=log_tail)


def list_renders(*, root: Optional[PathLike] = None, limit: int = 20, hooks: Optional[Hooks] = None,
                 renders_dir: Optional[PathLike] = None) -> List[BundleInfo]:
    """Bundles under the project's renders dir, newest first."""
    if renders_dir is None:
        layout = _layout(root, hooks)
        rd = layout.renders_dir if layout else (Path(root) if root else Path.cwd()) / "renders"
    else:
        rd = Path(renders_dir)
    if not rd.is_dir():
        return []
    dirs = [p for p in rd.iterdir() if p.is_dir() and _STEM_RE.match(p.name)]
    dirs.sort(key=lambda p: p.name.rsplit("_", 1)[-1], reverse=True)
    return [_bundle_info(p) for p in dirs[: max(0, int(limit))]]


def describe_render(bundle: PathLike, *, root: Optional[PathLike] = None, hooks: Optional[Hooks] = None) -> BundleInfo:
    """Files, config snapshot, stats and log tail for one bundle (dir, stem, or snapshot yaml)."""
    p = Path(bundle)
    if not p.exists() and "/" not in str(bundle):
        for b in list_renders(root=root, limit=10_000, hooks=hooks):
            if b.stem == str(bundle):
                p = Path(b.bundle_dir)
                break
    if p.is_file():
        p = p.parent
    if not p.is_dir():
        raise CommandError(f"Render bundle not found: {bundle}")
    return _bundle_info(p.resolve(), detailed=True)


def project_info(*, root: Optional[PathLike] = None, hooks: Optional[Hooks] = None) -> Dict[str, Any]:
    """Root, layout, and the resolved project-level config."""
    hooks = hooks or Hooks()
    lc = load_layers(schema=hooks.schema, project_config=hooks.project_config, root=root, apply_viewer_env_vars=False)
    layout = lc.layout
    return {
        "root": str(lc.root) if lc.root else None,
        "layout": None if layout is None else {
            "configs_dirs": [str(p) for p in layout.configs_dirs],
            "src_dir": str(layout.src_dir),
            "renders_dir": str(layout.renders_dir),
        },
        "sources": [str(s) for s in lc.sources],
        "config": OmegaConf.to_container(lc.cfg, resolve=True),
    }


# --- scaffolding (see bevel_cad.scaffold) -----------------------------------------------------

