"""Unit tests for diagnostic reporting and visual overlay generation."""

from pathlib import Path
from uuid import uuid4
import pymupdf
import pytest

from tz_plan_pipeline.extraction import (
    DiagnosticOverlayRenderer,
    ExtractionReport,
    PageReportSummary,
    extract_dimension_candidates,
    extract_page_content,
    extract_scale_candidates,
)
from tz_plan_pipeline.ingestion.hasher import compute_file_sha256
from tests.fixtures.pdf_generators import create_synthetic_vector_plan_pdf


def test_extraction_report_markdown_and_json(tmp_path: Path):
    doc_id = uuid4()
    rev_id = uuid4()

    report = ExtractionReport(
        document_id=doc_id,
        revision_id=rev_id,
        filename="alaprajz.pdf",
        file_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        page_count=1,
        pages=[
            PageReportSummary(
                page_number=1,
                content_class="vector_only",
                width_pt=841.89,
                height_pt=595.28,
                rotation=0,
                text_spans=42,
                vector_paths=18,
                images=0,
                dimension_candidates=8,
                scale_candidates=["M 1:50"],
                warnings=["Unit assumed cm for 3 dimensions"]
            )
        ],
        total_text_spans=42,
        total_vector_paths=18,
        total_images=0,
        total_dimension_candidates=8,
        warnings=["Sample extraction warning"]
    )

    md = report.to_markdown()
    assert "# Extraction Report: alaprajz.pdf" in md
    assert "M 1:50" in md
    assert "841.9x595.3" in md
    assert "Sample extraction warning" in md

    # Save markdown and JSON
    md_file = tmp_path / "report.md"
    json_file = tmp_path / "report.json"
    report.save_markdown(md_file)
    report.save_json(json_file)

    assert md_file.exists()
    assert json_file.exists()
    assert md_file.stat().st_size > 0
    assert json_file.stat().st_size > 0


def test_diagnostic_overlay_png_rendering(tmp_path: Path):
    pdf_path = create_synthetic_vector_plan_pdf(tmp_path / "original_plan.pdf", pages=1)
    orig_sha = compute_file_sha256(pdf_path)

    doc = pymupdf.open(pdf_path)
    page_0 = doc[0]
    extracted = extract_page_content(page_0)
    dimensions = extract_dimension_candidates(extracted.text_spans, page_number=1)
    scales = extract_scale_candidates(extracted.text_spans, page_number=1)
    doc.close()

    png_out = tmp_path / "diagnostics" / "page_1_overlay.png"
    out = DiagnosticOverlayRenderer.render_overlay(
        source_pdf_path=pdf_path,
        page_number=1,
        output_path=png_out,
        extraction_result=extracted,
        dimension_candidates=dimensions,
        scale_candidates=scales,
        format="png",
        dpi=100.0
    )

    assert out.exists()
    assert out.stat().st_size > 1000  # Non-trivial image generated

    # Verify original PDF was NOT modified (Principle 11: Document Immutability)
    assert compute_file_sha256(pdf_path) == orig_sha


def test_diagnostic_overlay_pdf_rendering(tmp_path: Path):
    pdf_path = create_synthetic_vector_plan_pdf(tmp_path / "original_plan2.pdf", pages=1)
    orig_sha = compute_file_sha256(pdf_path)

    doc = pymupdf.open(pdf_path)
    page_0 = doc[0]
    extracted = extract_page_content(page_0)
    dimensions = extract_dimension_candidates(extracted.text_spans, page_number=1)
    scales = extract_scale_candidates(extracted.text_spans, page_number=1)
    doc.close()

    pdf_out = tmp_path / "diagnostics" / "page_1_diagnostic.pdf"
    out = DiagnosticOverlayRenderer.render_overlay(
        source_pdf_path=pdf_path,
        page_number=1,
        output_path=pdf_out,
        extraction_result=extracted,
        dimension_candidates=dimensions,
        scale_candidates=scales,
        format="pdf"
    )

    assert out.exists()
    diag_doc = pymupdf.open(out)
    assert len(diag_doc) == 1
    diag_doc.close()

    # Original remains immutable
    assert compute_file_sha256(pdf_path) == orig_sha
