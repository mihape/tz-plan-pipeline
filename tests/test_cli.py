"""Unit tests for the Typer CLI commands."""

from pathlib import Path
from typer.testing import CliRunner
from tz_plan_pipeline.cli.main import app

runner = CliRunner()


def test_cli_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "TZ Plan Pipeline version" in result.output
    assert "Hungary" in result.output


def test_cli_config_validate_valid():
    result = runner.invoke(app, ["config", "validate", "--config", "configs/default_config.yaml"])
    assert result.exit_code == 0
    assert "is valid" in result.output
    assert "default_config.yaml" in result.output


def test_cli_config_validate_missing_file():
    result = runner.invoke(app, ["config", "validate", "--config", "non_existent.yaml"])
    assert result.exit_code != 0
    assert "Configuration validation failed" in result.output


def test_cli_project_create_and_info(tmp_path: Path):
    proj_dir = tmp_path / "projects"
    # Create project
    res_create = runner.invoke(app, [
        "project", "create", "Családi Ház Budapest",
        "--code", "TZ-BP-001",
        "--desc", "Teszt projekt leírás",
        "--dir", str(proj_dir)
    ])
    assert res_create.exit_code == 0
    assert "Project created successfully" in res_create.output

    # List projects
    res_list = runner.invoke(app, ["project", "list", "--dir", str(proj_dir)])
    assert res_list.exit_code == 0
    assert "TZ-BP-001" in res_list.output
    assert "Családi Ház Budapest" in res_list.output

    # Info project
    res_info = runner.invoke(app, [
        "project", "info", "TZ-BP-001",
        "--dir", str(proj_dir)
    ])
    assert res_info.exit_code == 0
    assert "Családi Ház Budapest" in res_info.output
    assert "TZ-BP-001" in res_info.output
