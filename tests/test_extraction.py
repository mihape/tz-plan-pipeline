"""Unit tests for PDF inventory, object counting, content classification, and vector/text extraction."""

from pathlib import Path
import pymupdf
import pytest

from tz_plan_pipeline.extraction.inventory import (
    PageContentClass,
    classify_page_content,
    inspect_page_inventory,
)
from tz_plan_pipeline.extraction.pdf_extractor import (
    VectorCommandType,
    extract_page_content,
)
from tests.fixtures.pdf_generators import (
    create_synthetic_mixed_pdf,
    create_synthetic_raster_pdf,
    create_synthetic_vector_plan_pdf,
)


def test_classify_page_content_heuristics():
    # 1. Empty page
    cls, _ = classify_page_content(text_span_count=0, vector_path_count=0, image_count=0)
    assert cls == PageContentClass.EMPTY

    # 2. Raster only (scanned plan)
    cls, _ = classify_page_content(text_span_count=2, vector_path_count=0, image_count=1)
    assert cls == PageContentClass.RASTER_ONLY

    # 3. Vector only (CAD export)
    cls, _ = classify_page_content(text_span_count=100, vector_path_count=50, image_count=0)
    assert cls == PageContentClass.VECTOR_ONLY

    # 4. Mixed (CAD export with embedded photo / logo)
    cls, _ = classify_page_content(text_span_count=80, vector_path_count=40, image_count=2)
    assert cls == PageContentClass.MIXED


def test_extract_vector_plan_content(tmp_path: Path):
    pdf_path = create_synthetic_vector_plan_pdf(tmp_path / "plan.pdf", pages=2, include_scale_label="M 1:50")

    doc = pymupdf.open(pdf_path)
    assert len(doc) == 2

    page_0 = doc[0]
    result = extract_page_content(page_0)

    # Inventory
    assert result.page_number == 1
    assert result.inventory.content_class == PageContentClass.VECTOR_ONLY
    assert result.inventory.width_pt == pytest.approx(841.89)
    assert result.inventory.height_pt == pytest.approx(595.28)
    assert result.inventory.rotation == 0
    assert result.inventory.text_span_count > 0
    assert result.inventory.vector_path_count > 0
    assert len(result.inventory.scale_label_candidates) > 0

    # Text spans
    texts = [span.text for span in result.text_spans]
    assert any("ALAPRAJZ" in t for t in texts)
    assert any("150/150" in t for t in texts)
    assert any("5,00" in t for t in texts)
    assert any("+0,00" in t for t in texts)

    # Text span coordinates
    for span in result.text_spans:
        assert span.bbox.x0 <= span.bbox.x1
        assert span.bbox.y0 <= span.bbox.y1
        assert span.font_size > 0

    # Vector paths
    assert len(result.vector_paths) > 0
    line_commands = [
        cmd for v in result.vector_paths for cmd in v.items if cmd.command_type == VectorCommandType.LINE
    ]
    assert len(line_commands) > 0

    doc.close()


def test_extract_raster_content(tmp_path: Path):
    pdf_path = create_synthetic_raster_pdf(tmp_path / "scanned.pdf")
    doc = pymupdf.open(pdf_path)
    page_0 = doc[0]

    result = extract_page_content(page_0)
    assert result.inventory.content_class == PageContentClass.RASTER_ONLY
    assert result.inventory.image_count == 1
    assert len(result.images) == 1
    assert result.images[0].pixel_width == 600
    assert result.images[0].pixel_height == 800

    doc.close()


def test_extract_mixed_content(tmp_path: Path):
    pdf_path = create_synthetic_mixed_pdf(tmp_path / "mixed.pdf")
    doc = pymupdf.open(pdf_path)
    page_0 = doc[0]

    result = extract_page_content(page_0)
    assert result.inventory.content_class == PageContentClass.MIXED
    assert result.inventory.image_count == 1
    assert result.inventory.vector_path_count > 0
    assert len(result.text_spans) > 0

    doc.close()


def test_extract_rotated_page(tmp_path: Path):
    pdf_path = create_synthetic_vector_plan_pdf(tmp_path / "rotated.pdf", pages=1, rotation=90)
    doc = pymupdf.open(pdf_path)
    page_0 = doc[0]

    result = extract_page_content(page_0)
    assert result.inventory.rotation == 90
    assert result.inventory.content_class == PageContentClass.VECTOR_ONLY

    # Ensure all bounding boxes remain valid
    for span in result.text_spans:
        assert span.bbox.x0 <= span.bbox.x1
        assert span.bbox.y0 <= span.bbox.y1

    doc.close()
