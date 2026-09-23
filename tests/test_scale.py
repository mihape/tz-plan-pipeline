"""Unit tests for scale candidate extraction, multi-scale regions, and calibration verification."""

from pathlib import Path
from uuid import uuid4
import pymupdf
import pytest

from tz_plan_pipeline.core.coordinates import ScaleStatus
from tz_plan_pipeline.extraction.dimensions import extract_dimension_candidates
from tz_plan_pipeline.extraction.pdf_extractor import extract_page_content
from tz_plan_pipeline.extraction.scale import (
    DrawingScaleRegion,
    extract_scale_candidates,
    verify_scale_calibration,
)
from tz_plan_pipeline.models.common import BoundingBox
from tests.fixtures.pdf_generators import create_synthetic_vector_plan_pdf


def test_scale_label_candidate_extraction():
    from tz_plan_pipeline.extraction.pdf_extractor import ExtractedTextSpan

    spans = [
        ExtractedTextSpan(text="FÖLDSZINTI ALAPRAJZ", bbox=BoundingBox(x0=0, y0=0, x1=10, y1=10), font_size=12),
        ExtractedTextSpan(text="Méretarány: M 1:50", bbox=BoundingBox(x0=0, y0=0, x1=10, y1=10), font_size=10),
        ExtractedTextSpan(text="Metszet 1:20", bbox=BoundingBox(x0=0, y0=0, x1=10, y1=10), font_size=10),
        ExtractedTextSpan(text="Normál szöveg 123", bbox=BoundingBox(x0=0, y0=0, x1=10, y1=10), font_size=10),
    ]

    candidates = extract_scale_candidates(spans, page_number=1)
    assert len(candidates) == 2
    ratios = [c.declared_ratio for c in candidates]
    assert 50.0 in ratios
    assert 20.0 in ratios


def test_scale_calibration_verification_with_matching_geometry(tmp_path: Path):
    # Generates plan with exact 5.00m dimension line at 1:50 scale
    pdf_path = create_synthetic_vector_plan_pdf(tmp_path / "plan_calib.pdf", pages=1, include_scale_label="M 1:50")
    doc = pymupdf.open(pdf_path)
    page_0 = doc[0]

    extracted = extract_page_content(page_0)
    dimensions = extract_dimension_candidates(extracted.text_spans, page_number=1)
    scale_candidates = extract_scale_candidates(extracted.text_spans, page_number=1)

    assert len(scale_candidates) > 0
    scale_cand = scale_candidates[0]
    assert scale_cand.declared_ratio == 50.0

    project_id = uuid4()
    scale, finding = verify_scale_calibration(
        scale_candidate=scale_cand,
        dimension_candidates=dimensions,
        vector_paths=extracted.vector_paths,
        project_id=project_id,
        tolerance_percent=1.5
    )

    # Verification should succeed against the 5,00 dimension line!
    assert scale.status == ScaleStatus.CALIBRATED
    assert scale.is_authoritative()
    assert scale.calibrated_ratio == pytest.approx(50.0, rel=0.01)
    assert finding is None

    doc.close()


def test_scale_unverified_creates_audit_finding():
    from tz_plan_pipeline.extraction.scale import ScaleCandidate
    from tz_plan_pipeline.models.enums import FindingSeverity

    cand = ScaleCandidate(
        label="M 1:100",
        declared_ratio=100.0,
        bbox=BoundingBox(x0=10, y0=10, x1=50, y1=20),
        page_number=1
    )

    project_id = uuid4()
    # No matching dimension lines provided
    scale, finding = verify_scale_calibration(
        scale_candidate=cand,
        dimension_candidates=[],
        vector_paths=[],
        project_id=project_id
    )

    # Scale must remain uncalibrated (DECLARED)
    assert scale.status == ScaleStatus.DECLARED
    assert not scale.is_authoritative()

    # Must create a review finding
    assert finding is not None
    assert finding.severity == FindingSeverity.WARNING
    assert "could not be authoritatively calibrated" in finding.description


def test_multi_scale_drawing_region_model():
    r1 = DrawingScaleRegion(
        name="Alaprajz 1:100",
        bbox=BoundingBox(x0=0, y0=0, x1=500, y1=500)
    )
    r2 = DrawingScaleRegion(
        name="Csomópont 1:20",
        bbox=BoundingBox(x0=500, y0=0, x1=800, y1=500)
    )
    assert r1.id != r2.id
    assert r1.name == "Alaprajz 1:100"
    assert r2.name == "Csomópont 1:20"


def test_conflicting_multiple_scale_labels_on_single_page():
    """Verify that multiple scale candidates on one page do not default to a single global scale."""
    from tz_plan_pipeline.extraction.pdf_extractor import ExtractedTextSpan

    spans = [
        ExtractedTextSpan(text="Földszinti alaprajz M 1:100", bbox=BoundingBox(x0=100, y0=100, x1=250, y1=120), font_size=10),
        ExtractedTextSpan(text="Homlokzati metszet M 1:50", bbox=BoundingBox(x0=400, y0=100, x1=550, y1=120), font_size=10),
        ExtractedTextSpan(text="Lábazati részletrajz 1:20", bbox=BoundingBox(x0=600, y0=100, x1=750, y1=120), font_size=10),
    ]

    candidates = extract_scale_candidates(spans, page_number=1)
    assert len(candidates) == 3
    ratios = {c.declared_ratio for c in candidates}
    assert ratios == {100.0, 50.0, 20.0}

