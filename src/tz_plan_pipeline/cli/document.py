"""CLI commands for document ingestion, inspection, extraction, and diagnostic reporting."""

from pathlib import Path
from typing import Optional
from uuid import UUID
import pymupdf
from rich.console import Console
from rich.table import Table
import typer

from tz_plan_pipeline.core.db import DatabaseManager, ProjectRepository
from tz_plan_pipeline.core.logging import setup_logging
from tz_plan_pipeline.extraction import (
    DiagnosticOverlayRenderer,
    ExtractionReport,
    PageReportSummary,
    extract_dimension_candidates,
    extract_page_content,
    extract_scale_candidates,
    inspect_page_inventory,
)
from tz_plan_pipeline.ingestion import DocumentIngestionService, IngestionStatus
from tz_plan_pipeline.models import Document, DocumentType, Evidence, EvidenceSourceType, Project
from tz_plan_pipeline.models.common import BoundingBox

document_app = typer.Typer(
    name="document",
    help="Manage architectural drawing documents, ingestion, and extraction."
)
console = Console()


def resolve_project_and_repo(
    project_identifier: str,
    projects_dir: Path = Path("projects")
) -> tuple[Project, ProjectRepository, Path]:
    """Resolve project and repository from code, UUID, or folder path."""
    # Check if direct folder
    p_path = Path(project_identifier)
    if p_path.is_dir() and (p_path / "project.db").exists():
        project_folder = p_path
    else:
        project_folder = projects_dir / project_identifier

    db_path = project_folder / "project.db"
    if not db_path.exists():
        console.print(f"[bold red]Error: Project database not found at '{db_path}'.[/bold red]")
        raise typer.Exit(code=1)

    db_manager = DatabaseManager(db_path)
    repo = ProjectRepository(db_manager)

    # Find project record
    projects = repo.list_projects()
    if not projects:
        console.print(f"[bold red]Error: No project record inside '{db_path}'.[/bold red]")
        raise typer.Exit(code=1)

    # Match by code or id if multiple
    target_project = projects[0]
    for p in projects:
        if p.code.lower() == project_identifier.lower() or str(p.id) == project_identifier:
            target_project = p
            break

    return target_project, repo, project_folder


@document_app.command("import")
def import_document(
    project_id: str = typer.Option(..., "--project", "-p", help="Project code or UUID"),
    input_path: Path = typer.Option(..., "--input", "-i", help="Path to PDF file or directory"),
    doc_type: str = typer.Option("architectural_plan", "--type", "-t", help="Document type category"),
    projects_dir: Path = typer.Option(Path("projects"), "--dir", help="Root projects directory")
):
    """Ingest immutable PDF drawing files into an existing project."""
    setup_logging()
    project, repo, project_folder = resolve_project_and_repo(project_id, projects_dir)
    service = DocumentIngestionService(repo, project_folder)

    try:
        dt = DocumentType(doc_type.lower())
    except ValueError:
        dt = DocumentType.ARCHITECTURAL_PLAN

    target = Path(input_path)
    if target.is_file():
        results = [service.ingest_file(project.id, target, doc_type=dt)]
    elif target.is_dir():
        results = service.ingest_directory(project.id, target, doc_type=dt)
    else:
        console.print(f"[bold red]Error: Input path '{input_path}' not found.[/bold red]")
        raise typer.Exit(code=1)

    table = Table(title=f"Ingestion Results for Project {project.code}", show_header=True, header_style="bold cyan")
    table.add_column("Filename", style="bold")
    table.add_column("Status")
    table.add_column("Revision")
    table.add_column("SHA-256 (12 chars)")
    table.add_column("Pages")
    table.add_column("Message")

    for r in results:
        status_color = "green" if "success" in r.status else ("yellow" if "duplicate" in r.status else "red")
        sha_short = r.file_hash[:12] if r.file_hash else "-"
        rev = r.revision_code or "-"
        table.add_row(
            r.filename,
            f"[{status_color}]{r.status}[/{status_color}]",
            rev,
            sha_short,
            str(r.page_count),
            r.message
        )

    console.print(table)


@document_app.command("list")
def list_documents(
    project_id: str = typer.Option(..., "--project", "-p", help="Project code or UUID"),
    projects_dir: Path = typer.Option(Path("projects"), "--dir", help="Root projects directory")
):
    """List all registered documents and current active revisions for a project."""
    project, repo, _ = resolve_project_and_repo(project_id, projects_dir)
    docs = repo.list_documents(project.id)

    if not docs:
        console.print(f"[yellow]No documents registered in project '{project.code}'.[/yellow]")
        return

    table = Table(title=f"Documents in {project.name} ({project.code})", show_header=True, header_style="bold cyan")
    table.add_column("Filename", style="bold", overflow="fold")
    table.add_column("Doc Type")
    table.add_column("Latest Rev")
    table.add_column("Active Hash (SHA-256)")
    table.add_column("Pages")
    table.add_column("Registered At")

    for d in docs:
        latest = repo.get_latest_revision(d.id)
        rev_code = latest.revision_code if latest else "-"
        hash_disp = latest.file_hash[:16] + "..." if latest else "-"
        pages = repo.get_pages(latest.id) if latest else []
        table.add_row(
            d.filename,
            d.doc_type.value,
            rev_code,
            hash_disp,
            str(len(pages)),
            d.created_at.strftime("%Y-%m-%d %H:%M")
        )

    console.print(table)


@document_app.command("inspect")
def inspect_document(
    project_id: str = typer.Option(..., "--project", "-p", help="Project code or UUID"),
    doc_id: Optional[str] = typer.Option(None, "--doc-id", "-d", help="Document UUID or filename"),
    projects_dir: Path = typer.Option(Path("projects"), "--dir", help="Root projects directory")
):
    """Inspect page inventory, vector/raster classifications, and object counts."""
    project, repo, project_folder = resolve_project_and_repo(project_id, projects_dir)
    docs = repo.list_documents(project.id)

    if not docs:
        console.print(f"[yellow]No documents found in project '{project.code}'.[/yellow]")
        return

    target_docs = docs
    if doc_id:
        target_docs = [d for d in docs if str(d.id) == doc_id or d.filename.lower() == doc_id.lower()]
        if not target_docs:
            console.print(f"[bold red]Document '{doc_id}' not found in project.[/bold red]")
            raise typer.Exit(code=1)

    for doc in target_docs:
        latest = repo.get_latest_revision(doc.id)
        if not latest:
            continue

        pdf_path = project_folder / latest.source_path
        if not pdf_path.exists():
            console.print(f"[red]Stored PDF file not found at {pdf_path}[/red]")
            continue

        pdf_doc = pymupdf.open(pdf_path)
        table = Table(title=f"Inventory: {doc.filename} ({latest.revision_code})", show_header=True, header_style="bold cyan")
        table.add_column("Page", style="bold")
        table.add_column("Dimensions (pt)")
        table.add_column("Rotation")
        table.add_column("Class", style="magenta")
        table.add_column("Text Spans")
        table.add_column("Vector Paths")
        table.add_column("Images")
        table.add_column("Scale Candidates")

        for page in pdf_doc:
            inv = inspect_page_inventory(page)
            scales = ", ".join(inv.scale_label_candidates) or "-"
            table.add_row(
                str(inv.page_number),
                f"{inv.width_pt:.1f} x {inv.height_pt:.1f}",
                f"{inv.rotation}°",
                inv.content_class.value,
                str(inv.text_span_count),
                str(inv.vector_path_count),
                str(inv.image_count),
                scales
            )

        pdf_doc.close()
        console.print(table)


@document_app.command("extract")
def extract_document(
    project_id: str = typer.Option(..., "--project", "-p", help="Project code or UUID"),
    doc_id: Optional[str] = typer.Option(None, "--doc-id", "-d", help="Document UUID or filename"),
    page_num: Optional[int] = typer.Option(None, "--page", help="Specific 1-indexed page number"),
    projects_dir: Path = typer.Option(Path("projects"), "--dir", help="Root projects directory")
):
    """Extract text spans, vector geometry, and Hungarian dimension candidates into evidence."""
    setup_logging()
    project, repo, project_folder = resolve_project_and_repo(project_id, projects_dir)
    docs = repo.list_documents(project.id)

    if not docs:
        console.print(f"[yellow]No documents found in project '{project.code}'.[/yellow]")
        return

    target_docs = docs
    if doc_id:
        target_docs = [d for d in docs if str(d.id) == doc_id or d.filename.lower() == doc_id.lower()]
        if not target_docs:
            console.print(f"[bold red]Document '{doc_id}' not found in project.[/bold red]")
            raise typer.Exit(code=1)

    for doc in target_docs:
        latest = repo.get_latest_revision(doc.id)
        if not latest:
            continue

        pdf_path = project_folder / latest.source_path
        pdf_doc = pymupdf.open(pdf_path)

        stored_pages = repo.get_pages(latest.id)
        pages_to_process = stored_pages
        if page_num:
            pages_to_process = [p for p in stored_pages if p.page_number == page_num]

        total_evidence_saved = 0
        total_dims_found = 0

        for page_record in pages_to_process:
            pdf_page = pdf_doc[page_record.page_number - 1]
            extraction = extract_page_content(pdf_page)
            dims = extract_dimension_candidates(extraction.text_spans, page_record.page_number, doc.id)
            total_dims_found += len(dims)

            # Persist extracted dimension candidates as Evidence in SQLite
            for dim in dims:
                evidence = Evidence(
                    page_id=page_record.id,
                    bounding_box=dim.bbox,
                    source_type=EvidenceSourceType.CAD_TEXT,
                    text_content=dim.raw_text,
                    confidence=0.95,
                    raw_metadata={
                        "dimension_type": dim.dimension_type.value,
                        "normalized_value": dim.normalized_value,
                        "secondary_value": dim.secondary_value,
                        "unit": dim.unit.value if dim.unit else None,
                        "warnings": dim.warnings
                    }
                )
                repo.save_evidence(evidence)
                total_evidence_saved += 1

        pdf_doc.close()
        console.print(f"[bold green][OK] Extraction complete for '{doc.filename}' ({latest.revision_code}):[/bold green]")
        console.print(f"  Processed {len(pages_to_process)} page(s)")
        console.print(f"  Found {total_dims_found} dimension candidate(s)")
        console.print(f"  Saved {total_evidence_saved} Evidence record(s) to SQLite")


@document_app.command("report")
def generate_report(
    project_id: str = typer.Option(..., "--project", "-p", help="Project code or UUID"),
    doc_id: Optional[str] = typer.Option(None, "--doc-id", "-d", help="Document UUID or filename"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="Diagnostics output folder"),
    projects_dir: Path = typer.Option(Path("projects"), "--dir", help="Root projects directory")
):
    """Generate diagnostic extraction report and visual overlay files."""
    setup_logging()
    project, repo, project_folder = resolve_project_and_repo(project_id, projects_dir)
    docs = repo.list_documents(project.id)

    if not docs:
        console.print(f"[yellow]No documents found in project '{project.code}'.[/yellow]")
        return

    diag_dir = output_dir or (project_folder / "diagnostics")
    diag_dir.mkdir(parents=True, exist_ok=True)

    target_docs = docs
    if doc_id:
        target_docs = [d for d in docs if str(d.id) == doc_id or d.filename.lower() == doc_id.lower()]

    for doc in target_docs:
        latest = repo.get_latest_revision(doc.id)
        if not latest:
            continue

        pdf_path = project_folder / latest.source_path
        pdf_doc = pymupdf.open(pdf_path)

        pages = repo.get_pages(latest.id)
        page_summaries: list[PageReportSummary] = []

        total_text = 0
        total_vectors = 0
        total_images = 0
        total_dims = 0

        for p in pages:
            pdf_page = pdf_doc[p.page_number - 1]
            extracted = extract_page_content(pdf_page)
            dims = extract_dimension_candidates(extracted.text_spans, p.page_number, doc.id)
            scales = extract_scale_candidates(extracted.text_spans, p.page_number)

            total_text += len(extracted.text_spans)
            total_vectors += len(extracted.vector_paths)
            total_images += len(extracted.images)
            total_dims += len(dims)

            page_summaries.append(PageReportSummary(
                page_number=p.page_number,
                content_class=extracted.inventory.content_class.value,
                width_pt=extracted.inventory.width_pt,
                height_pt=extracted.inventory.height_pt,
                rotation=extracted.inventory.rotation,
                text_spans=len(extracted.text_spans),
                vector_paths=len(extracted.vector_paths),
                images=len(extracted.images),
                dimension_candidates=len(dims),
                scale_candidates=[s.label for s in scales]
            ))

            # Generate visual overlays (PNG + PDF) for each page
            overlay_png = diag_dir / f"{doc.id}_{latest.revision_code}_p{p.page_number}_diagnostic.png"
            DiagnosticOverlayRenderer.render_overlay(
                source_pdf_path=pdf_path,
                page_number=p.page_number,
                output_path=overlay_png,
                extraction_result=extracted,
                dimension_candidates=dims,
                scale_candidates=scales,
                format="png",
                dpi=150.0
            )

            overlay_pdf = diag_dir / f"{doc.id}_{latest.revision_code}_p{p.page_number}_diagnostic.pdf"
            DiagnosticOverlayRenderer.render_overlay(
                source_pdf_path=pdf_path,
                page_number=p.page_number,
                output_path=overlay_pdf,
                extraction_result=extracted,
                dimension_candidates=dims,
                scale_candidates=scales,
                format="pdf"
            )

        pdf_doc.close()

        # Build and save report
        report = ExtractionReport(
            document_id=doc.id,
            revision_id=latest.id,
            filename=doc.filename,
            file_hash=latest.file_hash,
            page_count=len(pages),
            pages=page_summaries,
            total_text_spans=total_text,
            total_vector_paths=total_vectors,
            total_images=total_images,
            total_dimension_candidates=total_dims
        )

        md_path = diag_dir / f"{doc.id}_{latest.revision_code}_report.md"
        json_path = diag_dir / f"{doc.id}_{latest.revision_code}_report.json"
        report.save_markdown(md_path)
        report.save_json(json_path)

        console.print(f"[bold green][OK] Diagnostic report generated for '{doc.filename}':[/bold green]")
        console.print(f"  Markdown: {md_path}")
        console.print(f"  JSON:     {json_path}")
        console.print(f"  Overlays: {diag_dir}")
