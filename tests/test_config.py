"""Unit tests for configuration loading and validation."""

from pathlib import Path
import pytest
from tz_plan_pipeline.core.config import PipelineConfig, load_config, save_config
from tz_plan_pipeline.core.errors import ConfigurationError


def test_load_default_config():
    config = load_config(Path("configs/default_config.yaml"))
    assert config.log_level == "INFO"
    assert config.storage.sqlite_filename == "project.db"
    assert config.defaults.country_code == "HU"
    assert config.ai.default_provider == "mock"


def test_missing_config_file_raises_error():
    with pytest.raises(ConfigurationError, match="Configuration file not found"):
        load_config(Path("non_existent_config.yaml"))


def test_save_and_reload_config(tmp_path: Path):
    cfg_file = tmp_path / "custom_config.yaml"
    cfg = PipelineConfig(log_level="DEBUG")
    save_config(cfg, cfg_file)

    loaded = load_config(cfg_file)
    assert loaded.log_level == "DEBUG"
