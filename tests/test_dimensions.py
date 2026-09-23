"""Unit tests for Hungarian architectural dimension candidate extraction."""

import pytest
from tz_plan_pipeline.extraction.dimensions import (
    DimensionCandidateType,
    extract_dimension_candidate_from_span,
    extract_dimension_candidates,
)
from tz_plan_pipeline.extraction.pdf_extractor import ExtractedTextSpan
from tz_plan_pipeline.models.common import BoundingBox
from tz_plan_pipeline.models.enums import Unit


def make_span(text: str) -> ExtractedTextSpan:
    return ExtractedTextSpan(
        text=text,
        bbox=BoundingBox(x0=10.0, y0=20.0, x1=50.0, y1=30.0),
        font_name="Arial",
        font_size=9.0
    )


def test_opening_callout_extraction():
    cand1 = extract_dimension_candidate_from_span(make_span("150/150"), page_number=1)
    assert cand1 is not None
    assert cand1.dimension_type == DimensionCandidateType.OPENING_CALLOUT
    assert cand1.normalized_value == 150.0
    assert cand1.secondary_value == 150.0
    assert cand1.unit == Unit.CM
    assert cand1.is_verified is False

    cand2 = extract_dimension_candidate_from_span(make_span("90/210"), page_number=1)
    assert cand2 is not None
    assert cand2.normalized_value == 90.0
    assert cand2.secondary_value == 210.0
    assert cand2.unit == Unit.CM


def test_sill_height_extraction():
    cand1 = extract_dimension_candidate_from_span(make_span("pm. 90"), page_number=1)
    assert cand1 is not None
    assert cand1.dimension_type == DimensionCandidateType.SILL_HEIGHT
    assert cand1.normalized_value == 90.0
    assert cand1.unit == Unit.CM
    assert cand1.is_verified is False

    cand2 = extract_dimension_candidate_from_span(make_span("pm 120"), page_number=1)
    assert cand2 is not None
    assert cand2.normalized_value == 120.0


def test_level_mark_extraction():
    # Zero level
    cand_zero = extract_dimension_candidate_from_span(make_span("+0,00"), page_number=1)
    assert cand_zero is not None
    assert cand_zero.dimension_type == DimensionCandidateType.LEVEL_MARK
    assert cand_zero.normalized_value == 0.0
    assert cand_zero.unit == Unit.M

    # Positive level
    cand_pos = extract_dimension_candidate_from_span(make_span("+2,80"), page_number=1)
    assert cand_pos is not None
    assert cand_pos.normalized_value == 2.80
    assert cand_pos.unit == Unit.M

    # Negative level
    cand_neg = extract_dimension_candidate_from_span(make_span("-1,45"), page_number=1)
    assert cand_neg is not None
    assert cand_neg.normalized_value == -1.45
    assert cand_neg.unit == Unit.M


def test_hungarian_decimal_linear_dimension():
    cand = extract_dimension_candidate_from_span(make_span("5,00"), page_number=1)
    assert cand is not None
    assert cand.dimension_type == DimensionCandidateType.LINEAR_DIMENSION
    assert cand.normalized_value == 5.00
    assert cand.unit == Unit.M


def test_explicit_units():
    cand_cm = extract_dimension_candidate_from_span(make_span("120 cm"), page_number=1)
    assert cand_cm is not None
    assert cand_cm.dimension_type == DimensionCandidateType.EXPLICIT_UNIT
    assert cand_cm.normalized_value == 120.0
    assert cand_cm.unit == Unit.CM

    cand_mm = extract_dimension_candidate_from_span(make_span("2400 mm"), page_number=1)
    assert cand_mm is not None
    assert cand_mm.normalized_value == 2400.0
    assert cand_mm.unit == Unit.MM


def test_integer_dimensions_in_cm():
    cand = extract_dimension_candidate_from_span(make_span("240"), page_number=1)
    assert cand is not None
    assert cand.dimension_type == DimensionCandidateType.LINEAR_DIMENSION
    assert cand.normalized_value == 240.0
    assert cand.unit == Unit.CM


def test_extract_all_candidates_from_spans():
    spans = [
        make_span("FÖLDSZINT"),      # Not a dimension
        make_span("150/150"),        # Opening
        make_span("pm. 90"),         # Sill
        make_span("random note"),    # Not a dimension
        make_span("+0,00"),          # Level
        make_span("5,00"),           # Linear
    ]
    candidates = extract_dimension_candidates(spans, page_number=1)
    assert len(candidates) == 4
    # All are unverified
    assert all(c.is_verified is False for c in candidates)


def test_missing_dimension_units_warning():
    """Verify that dimensions with implicit/missing units populate warnings."""
    cand = extract_dimension_candidate_from_span(make_span("38"), page_number=1)
    assert cand is not None
    assert len(cand.warnings) > 0
    assert "assumed centimeters" in cand.warnings[0]
