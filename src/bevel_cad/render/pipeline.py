"""
The render pipeline: one call turns a CadQuery part into a render bundle.

``render_part(part, cfg)`` plans the export jobs from ``rendering.exports``,
writes them into ``<output_dir>/<slug>_<timestamp>/`` (STL, STEP, 3MF, GLB,
GLTF, OBJ, preview PNG, config snapshot, stats CSV, log) and finally pushes
the geometry to cadquery-web-viewer when ``viewer.enabled`` is set.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import cadquery as cq
import trimesh
import yaml
from omegaconf import DictConfig, OmegaConf

from bevel_cad.config.paths import resolve_output_dir
from bevel_cad.mesh.convert import assembly_to_glb_bytes, glb_bytes_to_trimesh, solid_to_glb_bytes
from bevel_cad.render.colors import iter_assembly_leaf_solids
from bevel_cad.render.logbuffer import (
    attach_render_log_buffer,
    discard_render_log_buffer,
    finalize_render_log,
)
from bevel_cad.render.naming import body_slug, render_bundle_stem, resolve_filename_template
from bevel_cad.render.planner import ExportJob, RenderPlan, RenderPlanner, job_specs_from_config
from bevel_cad.render.preview import render_glb_to_image
from bevel_cad.render.stats import RenderStats

logger = logging.getLogger(__name__)

PartLike = Union[cq.Assembly, cq.Shape, cq.Workplane, trimesh.Trimesh, Any]


class ExportError(RuntimeError):
    """An export job could not be completed."""


# --- run context ----------------------------------------------------------------------------


@dataclass
class RunContext:
    """Everything a single render run needs to know before geometry exists."""

    cfg: DictConfig
    run_name: str
    stem: str
    bundle_dir: Path
    stats: RenderStats
    sources: Tuple[Any, ...] = ()
    root: Optional[Path] = None
    part_source: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.now)


def _name_from_target(target: str) -> str:
    """``src/foo.py`` -> ``foo``; ``pkg.mod:fn`` -> ``fn``; ``pkg.mod`` -> ``mod``; ``name`` -> ``name``."""
    s = str(target).strip()
    if ":" in s:
        s = s.rsplit(":", 1)[-1]
    if "/" in s or s.endswith(".py"):
        return Path(s).stem
    return s.rsplit(".", 1)[-1]


def resolve_run_name(
    cfg: Any, *, name: Optional[str] = None, part_name: Optional[str] = None, part_source: Optional[str] = None
) -> str:
    """``name`` > ``rendering.name`` > top-level ``name`` > part name > ``part`` target > ``"part"``."""
    if name:
        return str(name)
    for candidate in (OmegaConf.select(cfg, "rendering.name"), cfg.get("name")):
        if candidate not in (None, ""):
            return str(candidate)
    if part_name:
        return str(part_name)
    target = cfg.get("part") or part_source
    if target:
        derived = _name_from_target(str(target))
        if derived:
            return derived
    return "part"


def start_run(
    cfg: DictConfig,
    *,
    name: Optional[str] = None,
    now: Optional[datetime] = None,
    root: Optional[Path] = None,
    sources: Tuple[Any, ...] = (),
    part_source: Optional[str] = None,
    part_name: Optional[str] = None,
) -> RunContext:
    """Resolve run name / stem / bundle dir, start stats + log buffering. Creates no files."""
    run_name = resolve_run_name(cfg, name=name, part_name=part_name, part_source=part_source)
    stem = render_bundle_stem(run_name, now=now)
    bundle_dir = resolve_output_dir(cfg, root) / stem
    stats = RenderStats()
    stats.populate_config_sources(sources)
    stats.populate_git_info(cwd=root)
    stats.add_stat("render.run_name", run_name, "Resolved run name")
    stats.add_stat("render.bundle_dir", str(bundle_dir), "Render bundle output directory")
    if part_source:
        stats.add_stat("render.part", part_source, "Part target that produced the geometry")
    attach_render_log_buffer()
    return RunContext(
        cfg=cfg, run_name=run_name, stem=stem, bundle_dir=bundle_dir, stats=stats,
        sources=tuple(sources), root=root, part_source=part_source, started_at=now or datetime.now(),
    )


# --- result -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class RenderResult:
    run: RunContext
    plan: RenderPlan
    written: Dict[str, Path]
    extra_paths: Tuple[Path, ...]
    viewer_names: Tuple[str, ...]

    @property
    def bundle_dir(self) -> Path:
        return self.run.bundle_dir

    @property
    def stem(self) -> str:
        return self.run.stem

    @property
    def run_name(self) -> str:
        return self.run.run_name

    def path_for(self, fmt: str) -> Optional[Path]:
        for job in self.plan.execution_order:
            if job.format == fmt and job.name in self.written:
                return self.written[job.name]
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_name": self.run_name,
            "stem": self.stem,
            "bundle_dir": str(self.bundle_dir) if self.written else None,
            "files": {name: str(p) for name, p in self.written.items()},
            "extra_files": [str(p) for p in self.extra_paths],
            "viewer_names": list(self.viewer_names),
            "stats": {s.name: s.value for s in self.run.stats.stats},
        }


# --- artifacts ------------------------------------------------------------------------------


class PartArtifacts:
    """Normalises the input geometry and lazily builds STL / GLB once for every consumer."""

    def __init__(self, part: PartLike, run: RunContext) -> None:
        self.part = part
        self.run = run
        self.cfg = run.cfg
        self._solid: Optional[Any] = None
        self._assy: Optional[cq.Assembly] = None
        self._mesh: Optional[trimesh.Trimesh] = None
        self._is_assembly = False
        self._is_mesh = False
        self._normalized = False
        self.stl_written_path: Optional[Path] = None
        self.glb_bytes: Optional[bytes] = None
        self.extra_written_paths: List[Path] = []

    # normalisation -------------------------------------------------------------------------
    def _normalize(self) -> None:
        if self._normalized:
            return
        part = self.part
        if isinstance(part, cq.Assembly):
            self._is_assembly = True
            self._assy = part
            self._solid = part.toCompound()
        elif isinstance(part, trimesh.Trimesh):
            self._is_mesh = True
            self._mesh = part
        elif isinstance(part, cq.Shape):
            self._solid = part
        elif hasattr(part, "val"):  # cq.Workplane
            self._solid = part.val()
        elif hasattr(part, "wrapped"):  # build123d objects / anything wrapping a TopoDS_Shape
            self._solid = cq.Shape.cast(part.wrapped)
        else:
            raise TypeError(
                f"Unsupported part type {type(part).__name__}: expected a cadquery Assembly/Shape/Workplane, "
                "a trimesh.Trimesh, or an object exposing .wrapped"
            )
        self._normalized = True

    @property
    def solid(self) -> Any:
        self._normalize()
        return self._solid

    @property
    def assy(self) -> Optional[cq.Assembly]:
        self._normalize()
        return self._assy

    @property
    def is_assembly(self) -> bool:
        self._normalize()
        return self._is_assembly

    @property
    def is_mesh(self) -> bool:
        self._normalize()
        return self._is_mesh

    @property
    def mesh(self) -> Optional[trimesh.Trimesh]:
        self._normalize()
        return self._mesh

    def _tolerances(self) -> Tuple[float, float]:
        r = self.cfg.rendering
        return float(r.tolerance), float(r.angular_tolerance)

    # STL --------------------------------------------------------------------------------------
    def _export_solid_to_stl(self, dest: Path, *, ascii: bool) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if self.is_mesh:
            self.mesh.export(str(dest), file_type="stl_ascii" if ascii else "stl")
            return
        tol, ang = self._tolerances()
        cq.exporters.export(self.solid, str(dest), tolerance=tol, angularTolerance=ang, opt={"ascii": bool(ascii)})

    def ensure_stl_at(self, dest: Path, *, stl_ascii: bool = False) -> Path:
        if self.stl_written_path == dest and dest.exists():
            return dest
        self._export_solid_to_stl(dest, ascii=stl_ascii)
        self.stl_written_path = dest
        return dest

    def export_assembly_body_stls(self, merged_path: Path, *, stl_ascii: bool = False) -> List[Path]:
        """For assemblies with >= 2 bodies, write ``<stem>_<body>.stl`` next to the merged STL."""
        if not self.is_assembly or self.assy is None:
            return []
        leaves = iter_assembly_leaf_solids(self.assy)
        if len(leaves) < 2:
            return []
        tol, ang = self._tolerances()
        written: List[Path] = []
        seen: set = set()
        for name, obj in leaves:
            slug = body_slug(name)
            if slug in seen:
                raise ValueError(f"Assembly body names must be unique after slugging; duplicate: {slug!r}")
            seen.add(slug)
            dest = merged_path.with_name(f"{merged_path.stem}_{slug}{merged_path.suffix}")
            cq.exporters.export(obj, str(dest), tolerance=tol, angularTolerance=ang, opt={"ascii": bool(stl_ascii)})
            written.append(dest)
            logger.info("Exported body STL (%s) to %s", name, dest)
        self.extra_written_paths.extend(written)
        return written

    # GLB --------------------------------------------------------------------------------------
    def ensure_glb_bytes(self) -> bytes:
        if self.glb_bytes is not None:
            return self.glb_bytes
        if self.is_mesh and self.mesh is not None:
            self.glb_bytes = self.mesh.export(file_type="glb")
            return self.glb_bytes
        tol, ang = self._tolerances()
        if self.is_assembly and self.assy is not None:
            self.glb_bytes = assembly_to_glb_bytes(self.assy, tolerance=tol, angular_tolerance=ang)
        else:
            self.glb_bytes = solid_to_glb_bytes(self.solid, tolerance=tol, angular_tolerance=ang)
        return self.glb_bytes

    def bundle_glb_path(self) -> Optional[Path]:
        """Path of the planned GLB file (enabled or dependency-only), if any."""
        for spec in job_specs_from_config(self.cfg):
            if spec.format == "glb":
                return self.run.bundle_dir / resolve_filename_template(
                    spec.filename_template, bundle_stem=self.run.stem, run_name=self.run.run_name
                )
        return None

    # jobs -------------------------------------------------------------------------------------
    def execute_job(self, job: ExportJob) -> None:
        stage = f"render.job.{job.format}.{job.resolved_path.name}"
        with self.run.stats.record_stage(stage):
            if job.is_dependency_only:
                logger.info(
                    "Writing %s (required by %s; %s export disabled in config)",
                    job.resolved_path.name, job.dependency_of, job.format,
                )
            self._execute_job_inner(job)

    def _execute_job_inner(self, job: ExportJob) -> None:
        path = job.resolved_path
        path.parent.mkdir(parents=True, exist_ok=True)
        fmt = job.format

        if fmt == "stl":
            stl_ascii = bool(getattr(job.typed, "stl_ascii", False))
            self.ensure_stl_at(path, stl_ascii=stl_ascii)
            logger.info("Exported STL to %s", path)
            if not job.is_dependency_only:
                self.export_assembly_body_stls(path, stl_ascii=stl_ascii)
            return

        if fmt == "step":
            if self.is_mesh:
                raise ExportError("STEP export requires a B-rep solid but the part is a mesh; disable the step export.")
            if self.is_assembly and self.assy is not None:
                self.assy.export(
                    str(path), exportType="STEP", mode="default",
                    write_pcurves=bool(getattr(job.typed, "write_pcurves", True)),
                    precision_mode=int(getattr(job.typed, "precision_mode", 0)),
                )
            else:
                cq.exporters.export(self.solid, str(path), exportType="STEP")
            logger.info("Exported STEP to %s", path)
            return

        if fmt == "3mf":
            tol, ang = self._tolerances()
            if self.is_mesh and self.mesh is not None:
                self.mesh.export(str(path), file_type="3mf")
            else:
                cq.exporters.export(self.solid, str(path), exportType="3MF", tolerance=tol, angularTolerance=ang)
            logger.info("Exported 3MF to %s", path)
            return

        if fmt == "glb":
            path.write_bytes(self.ensure_glb_bytes())
            logger.info("Exported GLB to %s", path)
            return

        if fmt == "gltf":
            _export_gltf_embedded(self.ensure_glb_bytes(), path)
            logger.info("Exported GLTF to %s", path)
            return

        if fmt == "obj":
            _export_obj_from_glb(self.ensure_glb_bytes(), path, job.typed)
            return

        if fmt == "preview":
            _render_glb_bytes_to_image(self.ensure_glb_bytes(), path, job.typed)
            return

        if fmt == "config":
            self.write_config_yaml(path)
            return

        if fmt == "stats":
            self.run.stats.finalize_total_duration()
            self.run.stats.write_csv(path)
            logger.info("Exported stats CSV to %s", path)
            return

        raise ExportError(f"Unknown export format {fmt!r}")

    def write_config_yaml(self, path: Path) -> None:
        """Snapshot of the fully-resolved config; re-runnable via ``bevel render -c <snapshot>``."""
        data = OmegaConf.to_container(self.cfg, resolve=True)
        rendering = dict(data.get("rendering") or {})
        rendering["name"] = self.run.run_name
        data["rendering"] = rendering
        if self.run.part_source and not data.get("part"):
            data["part"] = self.run.part_source
        path.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False), encoding="utf-8")
        logger.info("Exported config YAML to %s", path)


def _render_glb_bytes_to_image(glb_bytes: bytes, image_path: Path, preview_settings: Any) -> None:
    with tempfile.NamedTemporaryFile(suffix=".glb", delete=False) as tf:
        tmp_glb = Path(tf.name)
    try:
        tmp_glb.write_bytes(glb_bytes)
        render_glb_to_image(tmp_glb, Path(image_path), preview_settings)
    finally:
        try:
            os.unlink(tmp_glb)
        except OSError:
            pass


def _export_gltf_embedded(glb_bytes: bytes, path: Path) -> None:
    """Write a single self-contained .gltf (buffers embedded as data URIs, no sidecar .bin)."""
    from trimesh.exchange.gltf import export_gltf

    mesh = glb_bytes_to_trimesh(glb_bytes)
    files = export_gltf(mesh, embed_buffers=True)
    gltf_name = next((k for k in files if k.endswith(".gltf")), None)
    if gltf_name is None:
        raise ExportError("trimesh did not produce a .gltf document")
    path.write_bytes(files[gltf_name])


def _export_obj_from_glb(glb_bytes: bytes, output_path: Path, obj_settings: Any) -> None:
    if output_path.suffix.lower() != ".obj":
        raise ExportError(f"OBJ export only supports the .obj extension (got {output_path.suffix!r}).")
    try:
        mesh = glb_bytes_to_trimesh(glb_bytes)
    except Exception as exc:
        raise ExportError(f"Failed to load GLB for OBJ export: {exc!r}") from exc
    if getattr(obj_settings, "unit_scale_mm_to_m", True):
        mesh.apply_scale(0.001)
    for fn in ("remove_degenerate_faces", "remove_unreferenced_vertices", "merge_vertices"):
        if hasattr(mesh, fn):
            getattr(mesh, fn)()
    if getattr(obj_settings, "watertight_required", False) and not mesh.is_watertight:
        raise ExportError("OBJ export aborted: generated mesh is not watertight.")
    target = getattr(obj_settings, "target_face_count", None)
    if target is not None and len(mesh.faces) > target > 0:
        mesh = mesh.simplify_quadratic_decimation(target)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(str(output_path), file_type="obj")
    logger.info("Exported mesh OBJ to %s", output_path)


# --- entry point ----------------------------------------------------------------------------

_LAST_RESULT: Optional["RenderResult"] = None


def consume_last_result() -> Optional["RenderResult"]:
    """Return (and forget) the most recent :func:`render_part` result in this process."""
    global _LAST_RESULT
    res, _LAST_RESULT = _LAST_RESULT, None
    return res



def render_part(
    part: PartLike,
    cfg: Union[DictConfig, RunContext],
    *,
    name: Optional[str] = None,
    viewer: Optional[bool] = None,
    root: Optional[Path] = None,
) -> RenderResult:
    """
    Render ``part`` into a bundle directory according to ``cfg`` and return what was written.

    ``cfg`` may be a loaded ``DictConfig`` or a :class:`RunContext` from :func:`start_run`
    (use the latter to record stage timings that happen before rendering).
    ``viewer`` overrides ``cfg.viewer.enabled``.
    """
    run = cfg if isinstance(cfg, RunContext) else start_run(cfg, name=name, root=root)
    plan = RenderPlanner.from_run(run, viewer=viewer)
    if not plan.has_side_effects:
        discard_render_log_buffer()
        logger.info("No export jobs enabled and viewer disabled; nothing to do.")
        return RenderResult(run=run, plan=plan, written={}, extra_paths=(), viewer_names=())

    if plan.want_viewer:
        from bevel_cad import viewer as viewer_mod

        viewer_mod.ensure_reachable(run.cfg)

    plan.bundle_dir.mkdir(parents=True, exist_ok=True)
    finalize_render_log(plan.bundle_dir / f"{run.stem}.log")
    logger.info("Render bundle destination: %s", plan.bundle_dir)

    ctx = PartArtifacts(part, run)
    ctx._normalize()
    if ctx.is_mesh and plan.needs_step_export:
        raise ExportError("STEP export requires a B-rep solid but the part is a mesh; disable the step export.")

    for job in plan.execution_order:
        ctx.execute_job(job)

    viewer_names: Tuple[str, ...] = ()
    if plan.want_viewer:
        from bevel_cad import viewer as viewer_mod

        viewer_names = tuple(viewer_mod.push_artifacts(ctx, run, name=run.run_name))

    written = {j.name: j.resolved_path for j in plan.jobs if j.resolved_path.exists()}
    logger.info("Wrote render bundle to %s/ (%d files)", plan.bundle_dir, len(written) + len(ctx.extra_written_paths))
    global _LAST_RESULT
    _LAST_RESULT = RenderResult(
        run=run, plan=plan, written=written, extra_paths=tuple(ctx.extra_written_paths), viewer_names=viewer_names
    )
    return _LAST_RESULT
