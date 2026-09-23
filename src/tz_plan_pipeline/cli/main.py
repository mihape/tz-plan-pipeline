"""Command-line interface for TZ Plan Pipeline using Typer."""

from pathlib import Path
from typing import Optional
from uuid import UUID
import typer
from rich.console import Console
from rich.table import Table

from tz_plan_pipeline.cli.document import document_app
from tz_plan_pipeline.core.config import PipelineConfig, load_config
from tz_plan_pipeline.core.db import DatabaseManager, ProjectRepository
from tz_plan_pipeline.core.logging import setup_logging
from tz_plan_pipeline.models import Project

__version__ = "0.1.0"

app = typer.Typer(
    name="tz",
    help="TZ Plan Pipeline: AI-assisted construction drawing analysis and quantity takeoff system.",
    no_args_is_help=True
)
project_app = typer.Typer(help="Manage construction takeoff projects.")
config_app = typer.Typer(help="View and validate pipeline configurations.")

app.add_typer(project_app, name="project")
app.add_typer(config_app, name="config")
app.add_typer(document_app, name="document")

console = Console()


@app.command("version")
def version_cmd():
    """Display TZ Plan Pipeline version and environment info."""
    console.print(f"[bold green]TZ Plan Pipeline[/bold green] version [bold cyan]{__version__}[/bold cyan]")
    console.print("Target Region: [yellow]Hungary (HU)[/yellow]")
    console.print("Core Architecture: [cyan]Deterministic Python SI Calculations[/cyan]")


# Project Subcommands

@project_app.command("create")
def create_project(
    name: str = typer.Argument(..., help="Name of the project"),
    code: str = typer.Option(..., "--code", "-c", help="Unique project code (e.g. 'TZ-2026-001')"),
    description: Optional[str] = typer.Option(None, "--desc", "-d", help="Project description"),
    projects_dir: Path = typer.Option(Path("projects"), "--dir", help="Directory where projects are stored")
):
    """Create a new takeoff project and initialize its SQLite database."""
    setup_logging()
    project_folder = projects_dir / code
    project_folder.mkdir(parents=True, exist_ok=True)
    db_path = project_folder / "project.db"

    db_manager = DatabaseManager(db_path)
    repo = ProjectRepository(db_manager)

    project = Project(name=name, code=code, description=description)
    repo.create_project(project)

    console.print(f"[bold green][OK] Project created successfully![/bold green]")
    console.print(f"  [cyan]ID:[/cyan] {project.id}")
    console.print(f"  [cyan]Name:[/cyan] {project.name}")
    console.print(f"  [cyan]Code:[/cyan] {project.code}")
    console.print(f"  [cyan]Location:[/cyan] {project_folder.resolve()}")
    console.print(f"  [cyan]Database:[/cyan] {db_path.name} (Schema v1, SQLite WAL)")


@project_app.command("list")
def list_projects(
    projects_dir: Path = typer.Option(Path("projects"), "--dir", help="Projects root directory")
):
    """List all projects in the specified projects directory."""
    if not projects_dir.exists():
        console.print(f"[yellow]No projects directory found at '{projects_dir.resolve()}'.[/yellow]")
        return

    table = Table(title="Takeoff Projects", show_header=True, header_style="bold cyan")
    table.add_column("Code", style="bold")
    table.add_column("Name")
    table.add_column("Created At")
    table.add_column("Database Path")

    found_any = False
    for p_dir in projects_dir.iterdir():
        if p_dir.is_dir() and (p_dir / "project.db").exists():
            db_manager = DatabaseManager(p_dir / "project.db")
            repo = ProjectRepository(db_manager)
            for proj in repo.list_projects():
                found_any = True
                table.add_row(
                    proj.code,
                    proj.name,
                    proj.created_at.strftime("%Y-%m-%d %H:%M"),
                    str(p_dir / "project.db")
                )

    if found_any:
        console.print(table)
    else:
        console.print(f"[yellow]No projects found in '{projects_dir.resolve()}'.[/yellow]")


@project_app.command("info")
def project_info(
    code_or_path: str = typer.Argument(..., help="Project code or path to project folder"),
    projects_dir: Path = typer.Option(Path("projects"), "--dir", help="Projects directory")
):
    """Display information about a specific project."""
    path_candidate = Path(code_or_path)
    if path_candidate.is_dir() and (path_candidate / "project.db").exists():
        db_path = path_candidate / "project.db"
    else:
        db_path = projects_dir / code_or_path / "project.db"

    if not db_path.exists():
        console.print(f"[red]Error: Project database not found at '{db_path}'.[/red]")
        raise typer.Exit(code=1)

    db_manager = DatabaseManager(db_path)
    repo = ProjectRepository(db_manager)
    projects = repo.list_projects()

    if not projects:
        console.print("[yellow]Database exists but contains no project records.[/yellow]")
        return

    proj = projects[0]
    elements = repo.get_building_elements(proj.id)

    console.print(f"[bold cyan]Project Details:[/bold cyan]")
    console.print(f"  [bold]Name:[/bold] {proj.name}")
    console.print(f"  [bold]Code:[/bold] {proj.code}")
    console.print(f"  [bold]ID:[/bold] {proj.id}")
    console.print(f"  [bold]Created:[/bold] {proj.created_at.isoformat()}")
    if proj.description:
        console.print(f"  [bold]Description:[/bold] {proj.description}")
    console.print(f"  [bold]Elements recorded:[/bold] {len(elements)}")


# Configuration Subcommands

@config_app.command("show")
def show_config(
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to config YAML")
):
    """Display active pipeline configuration."""
    cfg = load_config(config_path)
    console.print("[bold cyan]Active Configuration:[/bold cyan]")
    console.print(cfg.model_dump_json(indent=2))


@config_app.command("validate")
def validate_config(
    config_path: Path = typer.Option(..., "--config", "-c", help="Path to YAML file to validate")
):
    """Validate a YAML configuration file against schema."""
    try:
        cfg = load_config(config_path)
        console.print(f"[bold green][OK] Configuration at '{config_path}' is valid![/bold green]")
        console.print(f"  Log level: {cfg.log_level}")
        console.print(f"  Default provider: {cfg.ai.default_provider}")
        console.print(f"  Country code: {cfg.defaults.country_code}")
    except Exception as e:
        console.print(f"[bold red][ERROR] Configuration validation failed:[/bold red] {e}")
        raise typer.Exit(code=1)


def main():
    """Main CLI entrypoint."""
    app()


if __name__ == "__main__":
    main()
