"""Configuration models and YAML loader for TZ Plan Pipeline."""

from pathlib import Path
from typing import Optional
import yaml
from pydantic import BaseModel, Field

from tz_plan_pipeline.core.errors import ConfigurationError


class StorageConfig(BaseModel):
    """Storage directory configurations."""
    projects_dir: Path = Field(
        default=Path("projects"),
        description="Root directory where project folders and databases are kept"
    )
    sqlite_filename: str = Field(
        default="project.db",
        description="Filename of the SQLite database inside each project folder"
    )


class AIProviderConfig(BaseModel):
    """Configuration for AI provider interface."""
    default_provider: str = Field(
        default="mock",
        description="Identifier of the default AI provider ('mock', 'offline', etc.)"
    )
    timeout_seconds: float = Field(default=30.0, ge=1.0)
    max_retries: int = Field(default=3, ge=0)


class DefaultsConfig(BaseModel):
    """Domain defaults for Hungarian takeoff pipeline."""
    unit_system: str = Field(default="SI", description="Default unit system")
    scale_tolerance_percent: float = Field(default=1.0, ge=0.01)
    min_confidence_warning: float = Field(default=0.85, ge=0.0, le=1.0)
    country_code: str = Field(default="HU", description="Target region (Hungary)")


class PipelineConfig(BaseModel):
    """Master configuration for TZ Plan Pipeline."""
    log_level: str = Field(default="INFO")
    storage: StorageConfig = Field(default_factory=StorageConfig)
    ai: AIProviderConfig = Field(default_factory=AIProviderConfig)
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)


def load_config(config_path: Optional[Path] = None) -> PipelineConfig:
    """Load configuration from a YAML file, or return default if path is None or file doesn't exist."""
    if config_path is None:
        # Check standard default config location
        default_file = Path("configs/default_config.yaml")
        if default_file.exists():
            config_path = default_file
        else:
            return PipelineConfig()

    path = Path(config_path)
    if not path.exists():
        raise ConfigurationError(f"Configuration file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        raise ConfigurationError(f"Failed to parse YAML configuration at {path}: {e}") from e

    try:
        return PipelineConfig(**data)
    except Exception as e:
        raise ConfigurationError(f"Configuration validation failed for {path}: {e}") from e


def save_config(config: PipelineConfig, output_path: Path) -> None:
    """Write configuration out to a YAML file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Convert paths to strings for YAML dump
    data = config.model_dump(mode="json")
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
