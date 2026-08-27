"""Dependency-aware planning of render-bundle export jobs from ``rendering.exports``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from omegaconf import DictConfig, OmegaConf

from bevel_cad.config.schema import JOB_SETTINGS_TYPES, PreviewSettings
from bevel_cad.render.naming import DEFAULT_FILENAME_TEMPLATES, VALID_EXPORT_FORMATS, resolve_filename_template

# Execution phases (lower runs first). Mapping order in YAML is ignored.
_FORMAT_PHASE: Dict[str, int] = {
    "step": 10,
    "stl": 20,
    "3mf": 30,
    "glb": 40,
    "gltf": 50,
    "obj": 60,
    "preview": 70,
    "config": 80,
    "stats": 90,
}

# Formats that need another format's artifact; a disabled "dependency-only" job is
# synthesised when the dependency is not planned explicitly.
_DEPENDENCY_DEFAULTS: Dict[str, str] = {
    "preview": "glb",
    "obj": "glb",
    "gltf": "glb",
}

_RESERVED_JOB_KEYS = frozenset({"format", "enabled", "filename"})


class DuplicateExportFilenameError(ValueError):
    """Raised when two export jobs resolve to the same output path."""


@dataclass(frozen=True)
class JobSpec:
    """One entry of ``rendering.exports`` after defaults are applied."""

    name: str
    format: str
    enabled: bool
    filename_template: str
    settings: Dict[str, Any]


@dataclass(frozen=True)
class ExportJob:
    name: str
    format: str
    enabled: bool
    filename_template: str
    resolved_path: Path
    settings: Dict[str, Any]
    typed: Any = None  # validated per-format settings dataclass (StlSettings, PreviewSettings, ...)
    dependency_of: Optional[str] = None

    @property
    def is_dependency_only(self) -> bool:
        return not self.enabled and self.dependency_of is not None


@dataclass(frozen=True)
class RenderPlan:
    bundle_dir: Path
    bundle_stem: str
    run_name: str
    jobs: Tuple[ExportJob, ...]
    execution_order: Tuple[ExportJob, ...]
    want_viewer: bool

    @property
    def has_side_effects(self) -> bool:
        return bool(self.jobs) or self.want_viewer

    @property
    def needs_step_export(self) -> bool:
        return any(j.format == "step" for j in self.jobs)

    def job(self, name: str) -> Optional[ExportJob]:
        for j in self.jobs:
            if j.name == name:
                return j
        return None


def typed_settings(fmt: str, settings: Dict[str, Any]) -> Any:
    """Validate free-form job settings against the per-format dataclass (None if untyped)."""
    cls = JOB_SETTINGS_TYPES.get(fmt)
    if cls is None:
        if settings:
            raise ValueError(f"export format {fmt!r} takes no settings; got {sorted(settings)}")
        return None
    try:
        merged = OmegaConf.merge(OmegaConf.structured(cls), OmegaConf.create(dict(settings)))
        return OmegaConf.to_object(merged)
    except Exception as exc:
        raise ValueError(f"invalid settings for export format {fmt!r}: {exc}") from exc


def job_specs_from_config(cfg: Any) -> List[JobSpec]:
    """Read ``rendering.exports`` (mapping keyed by job name) into :class:`JobSpec` objects."""
    exports = OmegaConf.select(cfg, "rendering.exports") if isinstance(cfg, DictConfig) else cfg.rendering.exports
    if not exports:
        return []
    raw = OmegaConf.to_container(exports, resolve=True) if isinstance(exports, DictConfig) else dict(exports)
    specs: List[JobSpec] = []
    for name, entry in raw.items():
        entry = dict(entry or {})
        fmt = str(entry.get("format") or name).strip().lower()
        if fmt not in VALID_EXPORT_FORMATS:
            raise ValueError(
                f"rendering.exports.{name}: format must be one of {sorted(VALID_EXPORT_FORMATS)} (got {fmt!r})"
            )
        enabled = bool(entry.get("enabled", True))
        filename = str(entry.get("filename") or DEFAULT_FILENAME_TEMPLATES[fmt])
        settings = {k: v for k, v in entry.items() if k not in _RESERVED_JOB_KEYS}
        specs.append(JobSpec(name=str(name), format=fmt, enabled=enabled, filename_template=filename, settings=settings))
    return specs


def first_preview_settings(cfg: Any) -> Optional[PreviewSettings]:
    """Typed settings of the first enabled preview job (used for viewer colours / annotated PNGs)."""
    for spec in job_specs_from_config(cfg):
        if spec.format == "preview" and spec.enabled:
            return typed_settings("preview", spec.settings)
    for spec in job_specs_from_config(cfg):
        if spec.format == "preview":
            return typed_settings("preview", spec.settings)
    return None


def _validate_resolved_filename(name: str) -> None:
    if not name or name != Path(name).name or ".." in Path(name).parts:
        raise ValueError(f"Invalid export filename after template resolution: {name!r}")


def _job_from_spec(
    spec: JobSpec, *, bundle_dir: Path, bundle_stem: str, run_name: str,
    dependency_of: Optional[str] = None, enabled_override: Optional[bool] = None,
) -> ExportJob:
    resolved = resolve_filename_template(spec.filename_template, bundle_stem=bundle_stem, run_name=run_name)
    _validate_resolved_filename(resolved)
    return ExportJob(
        name=spec.name,
        format=spec.format,
        enabled=spec.enabled if enabled_override is None else enabled_override,
        filename_template=spec.filename_template,
        resolved_path=bundle_dir / resolved,
        settings=dict(spec.settings),
        typed=typed_settings(spec.format, spec.settings),
        dependency_of=dependency_of,
    )


def _ensure_dependency_jobs(jobs: List[ExportJob], *, bundle_dir: Path, bundle_stem: str, run_name: str) -> List[ExportJob]:
    by_path = {j.resolved_path for j in jobs}
    present = {j.format for j in jobs}
    added: List[ExportJob] = []
    for job in jobs:
        dep_fmt = _DEPENDENCY_DEFAULTS.get(job.format)
        if dep_fmt is None or dep_fmt in present:
            continue
        dep = _job_from_spec(
            JobSpec(name=dep_fmt, format=dep_fmt, enabled=False, filename_template=DEFAULT_FILENAME_TEMPLATES[dep_fmt], settings={}),
            bundle_dir=bundle_dir, bundle_stem=bundle_stem, run_name=run_name,
            dependency_of=job.name, enabled_override=False,
        )
        if dep.resolved_path in by_path:
            continue
        added.append(dep)
        by_path.add(dep.resolved_path)
        present.add(dep_fmt)
    return jobs + added


def _detect_duplicates(jobs: Sequence[ExportJob]) -> None:
    seen: Dict[Path, ExportJob] = {}
    for job in jobs:
        if job.resolved_path in seen:
            other = seen[job.resolved_path]
            raise DuplicateExportFilenameError(
                f"Duplicate export filename {job.resolved_path.name!r}: "
                f"{other.name} ({other.format}) and {job.name} ({job.format})"
            )
        seen[job.resolved_path] = job


def _sort_jobs(jobs: Sequence[ExportJob]) -> Tuple[ExportJob, ...]:
    return tuple(sorted(jobs, key=lambda j: (_FORMAT_PHASE.get(j.format, 100), j.filename_template)))


class RenderPlanner:
    @classmethod
    def plan(
        cls, cfg: Any, *, bundle_dir: Path, bundle_stem: str, run_name: str, viewer: Optional[bool] = None,
    ) -> RenderPlan:
        specs = [s for s in job_specs_from_config(cfg) if s.enabled]
        jobs = [_job_from_spec(s, bundle_dir=bundle_dir, bundle_stem=bundle_stem, run_name=run_name) for s in specs]
        jobs = _ensure_dependency_jobs(jobs, bundle_dir=bundle_dir, bundle_stem=bundle_stem, run_name=run_name)
        _detect_duplicates(jobs)
        want_viewer = bool(cfg.viewer.enabled) if viewer is None else bool(viewer)
        return RenderPlan(
            bundle_dir=bundle_dir,
            bundle_stem=bundle_stem,
            run_name=run_name,
            jobs=tuple(jobs),
            execution_order=_sort_jobs(jobs),
            want_viewer=want_viewer,
        )

    @classmethod
    def from_run(cls, run: Any, *, viewer: Optional[bool] = None) -> RenderPlan:
        return cls.plan(run.cfg, bundle_dir=run.bundle_dir, bundle_stem=run.stem, run_name=run.run_name, viewer=viewer)
