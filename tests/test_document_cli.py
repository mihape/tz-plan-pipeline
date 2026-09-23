"""Unit tests for document CLI commands (import, list, inspect, extract, report)."""

from pathlib import Path
from typer.testing import CliRunner
from tz_plan_pipeline.cli.main import app
from tests.fixtures.pdf_generators import create_synthetic_vector_plan_pdf

runner = CliRunner(env={"COLUMNS": "200"})


def test_document_cli_full_workflow(tmp_path: Path):
    proj_dir = tmp_path / "projects"
    proj_code = "TZ-DOC-001"

    # 1. Create a project
    res_proj = runner.invoke(app, [
        "project", "create", "Dokumentum Teszt Projekt",
        "--code", proj_code,
        "--dir", str(proj_dir)
    ])
    assert res_proj.exit_code == 0

    # 2. Generate a synthetic test PDF
    raw_pdf = tmp_path / "source_plan.pdf"
    create_synthetic_vector_plan_pdf(raw_pdf, pages=2, include_scale_label="M 1:50")

    # 3. Import document into project
    res_import = runner.invoke(app, [
        "document", "import",
        "--project", proj_code,
        "--input", str(raw_pdf),
        "--dir", str(proj_dir)
    ])
    assert res_import.exit_code == 0
    assert "source_plan.pdf" in res_import.output
    assert "rev01" in res_import.output

    # 4. List documents
    res_list = runner.invoke(app, [
        "document", "list",
        "--project", proj_code,
        "--dir", str(proj_dir)
    ])
    assert res_list.exit_code == 0
    assert "source_plan.pdf" in res_list.output
    assert "rev01" in res_list.output

    # 5. Inspect document
    res_inspect = runner.invoke(app, [
        "document", "inspect",
        "--project", proj_code,
        "--dir", str(proj_dir)
    ])
    assert res_inspect.exit_code == 0
    assert "vector_only" in res_inspect.output
    assert "M 1:50" in res_inspect.output

    # 6. Extract document candidates
    res_extract = runner.invoke(app, [
        "document", "extract",
        "--project", proj_code,
        "--dir", str(proj_dir)
    ])
    assert res_extract.exit_code == 0
    assert "Extraction complete" in res_extract.output
    assert "dimension candidate" in res_extract.output

    # 7. Generate diagnostic report and overlays
    diag_folder = tmp_path / "custom_diagnostics"
    res_report = runner.invoke(app, [
        "document", "report",
        "--project", proj_code,
        "--output-dir", str(diag_folder),
        "--dir", str(proj_dir)
    ])
    assert res_report.exit_code == 0
    assert "Diagnostic report generated" in res_report.output

    # Check generated report files
    md_reports = list(diag_folder.glob("*.md"))
    png_overlays = list(diag_folder.glob("*.png"))
    assert len(md_reports) >= 1
    assert len(png_overlays) >= 2  # 2 pages in synthetic plan
    assert md_reports[0].stat().st_size > 0
    assert png_overlays[0].stat().st_size > 1000
