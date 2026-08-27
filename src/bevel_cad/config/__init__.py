"""Layered YAML configuration (OmegaConf) and project layout discovery."""

from .loader import (
    ConfigError,
    ConfigSource,
    LoadedConfig,
    apply_viewer_env,
    config_to_dict,
    config_to_yaml,
    load_config,
    load_layers,
    normalize_layer,
)
from .paths import ENV_ROOT, LOCAL_FILE, PROJECT_FILE, ProjectLayout, find_project_root, resolve_output_dir
from .schema import (
    BevelSchema,
    ObjSettings,
    PreviewSettings,
    ProjectConfig,
    RenderingConfig,
    StepSettings,
    StlSettings,
    ViewerConfig,
    ViewerStyle,
    parse_color,
)

__all__ = [name for name in dir() if not name.startswith("_")]
