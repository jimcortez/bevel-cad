"""``bevel create`` / ``bevel add`` / ``bevel skills``: project scaffolding and templates."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from string import Template
from typing import Any, Dict, List, Mapping, Optional, Sequence

import yaml

from bevel_cad.config.paths import PROJECT_FILE, find_project_root

TEMPLATES_DIR = Path(__file__).with_name("templates")
SKILLS_DIR = Path(__file__).with_name("skills")
PRIMARY_FORMATS = ("stl", "step", "3mf", "glb")


class ScaffoldError(RuntimeError):
    pass


@dataclass
class TemplatePrompt:
    key: str
    prompt: str
    default: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class TemplateInfo:
    name: str
    description: str
    prompts: List[TemplatePrompt] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "description": self.description, "prompts": [p.to_dict() for p in self.prompts]}


@dataclass
class ScaffoldResult:
    root: str
    files: List[str]
    part_name: Optional[str] = None
    next_steps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


def _ident(name: str) -> str:
    """A valid python module / config key: lowercase, underscores."""
    s = re.sub(r"[^0-9a-zA-Z_]+", "_", name.strip()).strip("_").lower()
    if not s or s[0].isdigit():
        s = f"part_{s}"
    return s


def list_templates() -> List[TemplateInfo]:
    out = []
    for d in sorted(TEMPLATES_DIR.iterdir()):
        meta = d / "template.yaml"
        if not meta.is_file():
            continue
        data = yaml.safe_load(meta.read_text(encoding="utf-8")) or {}
        prompts = [TemplatePrompt(str(p["key"]), str(p.get("prompt", p["key"])), str(p.get("default", "")))
                   for p in data.get("prompts", []) or []]
        out.append(TemplateInfo(name=str(data.get("name", d.name)), description=str(data.get("description", "")), prompts=prompts))
    return out


def get_template(name: str) -> TemplateInfo:
    for t in list_templates():
        if t.name == name:
            return t
    raise ScaffoldError(f"Unknown template {name!r}; available: {', '.join(t.name for t in list_templates())}")


def _render(tmpl_path: Path, mapping: Mapping[str, Any]) -> str:
    return Template(tmpl_path.read_text(encoding="utf-8")).safe_substitute({k: str(v) for k, v in mapping.items()})


def _exports_block(primary: str) -> str:
    if primary not in PRIMARY_FORMATS:
        raise ScaffoldError(f"format must be one of {PRIMARY_FORMATS}, got {primary!r}")
    lines = []
    for fmt in ("stl", "step", "3mf", "glb"):
        enabled = fmt == primary or fmt == "glb"  # glb also feeds the preview and the viewer
        key = f'"{fmt}"' if fmt[0].isdigit() else fmt
        lines.append(f"    {key}: {{enabled: {'true' if enabled else 'false'}}}")
    return "\n".join(lines)


def _write(path: Path, text: str, *, force: bool, written: List[str]) -> None:
    if path.exists() and not force:
        raise ScaffoldError(f"{path} already exists (use --force to overwrite)")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    written.append(str(path))


def _part_files(root: Path, part_name: str, template: TemplateInfo, mapping: Dict[str, Any], *, force: bool, written: List[str]) -> None:
    tdir = TEMPLATES_DIR / template.name
    _write(root / "src" / f"{part_name}.py", _render(tdir / "part.py.tmpl", mapping), force=force, written=written)
    _write(root / "configs" / f"{part_name}.yaml", _render(tdir / "config.yaml.tmpl", mapping), force=force, written=written)


def resolve_prompt_values(template: TemplateInfo, params: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    values: Dict[str, str] = {}
    params = dict(params or {})
    for p in template.prompts:
        values[p.key] = str(params.pop(p.key, p.default))
    if params:
        raise ScaffoldError(f"template {template.name!r} does not take parameters: {sorted(params)}")
    return values


def create_project(
    name: str,
    *,
    description: str = "",
    format: str = "stl",
    template: str = "basic",
    directory: Optional[Path] = None,
    params: Optional[Mapping[str, Any]] = None,
    with_skills: bool = True,
    force: bool = False,
) -> ScaffoldResult:
    """Scaffold ``<directory or ./name>/`` with bevel.yaml, configs/, src/, renders/ and a first part."""
    if not name or not name.strip():
        raise ScaffoldError("project name is required")
    tinfo = None if template in (None, "", "none") else get_template(template)
    root = Path(directory) if directory else Path.cwd() / name
    root = root.resolve()
    if (root / PROJECT_FILE).exists() and not force:
        raise ScaffoldError(f"{root / PROJECT_FILE} already exists (use --force to overwrite)")
    part_name = _ident(name)
    mapping: Dict[str, Any] = {
        "name": name,
        "part_name": part_name,
        "description": description or (tinfo.description if tinfo else ""),
        "format": format,
        "exports_block": _exports_block(format),
        **(resolve_prompt_values(tinfo, params) if tinfo else {}),
    }
    written: List[str] = []
    pdir = TEMPLATES_DIR / "project"
    _write(root / PROJECT_FILE, _render(pdir / "bevel.yaml.tmpl", mapping), force=force, written=written)
    _write(root / "README.md", _render(pdir / "README.md.tmpl", mapping), force=force, written=written)
    _write(root / ".gitignore", _render(pdir / "gitignore.tmpl", mapping), force=force, written=written)
    (root / "renders").mkdir(parents=True, exist_ok=True)
    _write(root / "renders" / ".gitkeep", "", force=True, written=written)
    (root / "configs").mkdir(exist_ok=True)
    (root / "src").mkdir(exist_ok=True)
    if tinfo is not None:
        part_mapping = {**mapping, "name": part_name, "description": description or tinfo.description}
        _part_files(root, part_name, tinfo, part_mapping, force=force, written=written)
    else:
        part_name = None
    if with_skills:
        written.extend(install_skills(root / ".claude" / "skills", force=True))
    return ScaffoldResult(
        root=str(root), files=written, part_name=part_name,
        next_steps=[f"cd {root}"] + ([f"bevel render {part_name}", "bevel renders"] if part_name else []) + ["bevel add <name> --template basic|label"],
    )


def add_part(
    name: str,
    *,
    template: str = "basic",
    description: str = "",
    root: Optional[Path] = None,
    params: Optional[Mapping[str, Any]] = None,
    force: bool = False,
) -> ScaffoldResult:
    """Add ``src/<name>.py`` + ``configs/<name>.yaml`` to an existing project."""
    root_path = Path(root).resolve() if root else find_project_root()
    if root_path is None:
        raise ScaffoldError("Not inside a bevel project (no bevel.yaml found); run `bevel create` first or pass --root")
    tinfo = get_template(template)
    part_name = _ident(name)
    mapping = {"name": part_name, "part_name": part_name, "description": description or tinfo.description,
               **resolve_prompt_values(tinfo, params)}
    written: List[str] = []
    _part_files(root_path, part_name, tinfo, mapping, force=force, written=written)
    return ScaffoldResult(root=str(root_path), files=written, part_name=part_name, next_steps=[f"bevel render {part_name}"])


# --- skills ------------------------------------------------------------------------------------


@dataclass
class SkillInfo:
    name: str
    description: str
    path: str

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


def _frontmatter(text: str) -> Dict[str, Any]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    try:
        return yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError:
        return {}


def list_skills() -> List[SkillInfo]:
    out = []
    if not SKILLS_DIR.is_dir():
        return out
    for d in sorted(SKILLS_DIR.iterdir()):
        sk = d / "SKILL.md"
        if sk.is_file():
            fm = _frontmatter(sk.read_text(encoding="utf-8"))
            out.append(SkillInfo(name=str(fm.get("name", d.name)), description=str(fm.get("description", "")), path=str(d)))
    return out


def install_skills(dest: Path, *, force: bool = False, names: Sequence[str] = ()) -> List[str]:
    """Copy the bundled skill folders into ``dest`` (e.g. ``<project>/.claude/skills``)."""
    dest = Path(dest).expanduser().resolve()
    written: List[str] = []
    for skill in list_skills():
        if names and skill.name not in names:
            continue
        target = dest / Path(skill.path).name
        if target.exists():
            if not force:
                raise ScaffoldError(f"{target} already exists (use --force to overwrite)")
            shutil.rmtree(target)
        shutil.copytree(skill.path, target)
        written.append(str(target / "SKILL.md"))
    return written
