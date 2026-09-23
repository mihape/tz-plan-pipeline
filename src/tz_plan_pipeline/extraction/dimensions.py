"""Hungarian architectural dimension candidate extraction from drawing text layers."""

from enum import StrEnum
import re
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field

from tz_plan_pipeline.extraction.pdf_extractor import ExtractedTextSpan
from tz_plan_pipeline.models.common import BoundingBox
from tz_plan_pipeline.models.enums import Unit


class DimensionCandidateType(StrEnum):
    """Categorization of extracted dimension candidate."""
    OPENING_CALLOUT = "opening_callout"   # e.g. "150/150", "90/210" (width/height)
    SILL_HEIGHT = "sill_height"           # e.g. "pm. 90", "pm 90" (parapet height)
    LEVEL_MARK = "level_mark"             # e.g. "+0,00", "+2,80", "-0,15" (elevation)
    LINEAR_DIMENSION = "linear_dimension" # e.g. "5,00", "240", "38"
    EXPLICIT_UNIT = "explicit_unit"       # e.g. "120 cm", "2400 mm", "15.0 m"


class DimensionCandidate(BaseModel):
    """Represents an unverified candidate dimension extracted from a drawing text layer.

    Enforces Non-Negotiable Principle 4: Extracted/candidate values are unverified hypotheses.
    Enforces Non-Negotiable Principle 5: Missing data must never silently become zero.
    """
    raw_text: str = Field(description="Exact original text as found on drawing")
    dimension_type: DimensionCandidateType = Field(description="Detected dimension pattern")
    normalized_value: float = Field(description="Primary numerical value (Hungarian comma converted to decimal)")
    secondary_value: Optional[float] = Field(
        default=None,
        description="Secondary value if compound dimension (e.g. height in '150/150')"
    )
    unit: Optional[Unit] = Field(
        default=None,
        description="Unit if explicit or deduced by standard architectural convention"
    )
    bbox: BoundingBox = Field(description="Exact canonical bounding box of the text span")
    page_number: int = Field(ge=1, description="1-indexed physical page number")
    document_id: Optional[UUID] = Field(default=None, description="Source Document UUID")
    warnings: list[str] = Field(
        default_factory=list,
        description="Parsing warnings or heuristic unit assumptions"
    )
    is_verified: bool = Field(
        default=False,
        description="Always False upon extraction. Never treated as authoritative without verification."
    )


# Regex patterns for Hungarian construction drawings
RE_OPENING = re.compile(r"^(\d{2,4})\s*[/xX]\s*(\d{2,4})$")
RE_SILL = re.compile(r"^pm\.?\s*=?\s*(\d{1,4})$", re.IGNORECASE)
RE_LEVEL = re.compile(r"^([±\+\-])\s*(\d+[,.]\d{1,2})$")
RE_EXPLICIT = re.compile(r"^([+-]?\d+[,.]?\d*)\s*(m|cm|mm)$", re.IGNORECASE)
RE_DECIMAL_METERS = re.compile(r"^(\d+),(\d{2})$")  # Hungarian decimal with exactly 2 digits: "5,00", "2,40"
RE_INTEGER_CM = re.compile(r"^(\d{2,4})$")         # "240", "38", "120", "600"


def parse_hungarian_float(text: str) -> float:
    """Parse number string replacing Hungarian comma with dot."""
    cleaned = text.strip().replace("±", "").replace("+", "").replace(",", ".")
    return float(cleaned)


def extract_dimension_candidate_from_span(
    span: ExtractedTextSpan,
    page_number: int,
    document_id: Optional[UUID] = None
) -> Optional[DimensionCandidate]:
    """Attempt to parse an individual text span into a structured DimensionCandidate."""
    text = span.text.strip()
    if not text:
        return None

    # 1. Opening callout: "150/150", "90/210"
    match_opening = RE_OPENING.match(text)
    if match_opening:
        w_str, h_str = match_opening.group(1), match_opening.group(2)
        w, h = float(w_str), float(h_str)
        # In Hungarian floor plans, opening dimensions are specified in centimeters (e.g. 150 cm x 150 cm)
        return DimensionCandidate(
            raw_text=text,
            dimension_type=DimensionCandidateType.OPENING_CALLOUT,
            normalized_value=w,
            secondary_value=h,
            unit=Unit.CM,
            bbox=span.bbox,
            page_number=page_number,
            document_id=document_id,
            warnings=["Inferred unit: cm according to Hungarian architectural standard (MSZ)."]
        )

    # 2. Sill height (parapet): "pm. 90", "pm 90"
    match_sill = RE_SILL.match(text)
    if match_sill:
        val = float(match_sill.group(1))
        return DimensionCandidate(
            raw_text=text,
            dimension_type=DimensionCandidateType.SILL_HEIGHT,
            normalized_value=val,
            unit=Unit.CM,
            bbox=span.bbox,
            page_number=page_number,
            document_id=document_id,
            warnings=["Inferred unit: cm for window parapet height."]
        )

    # 3. Level mark: "+0,00", "+2,80", "-0,45"
    match_level = RE_LEVEL.match(text)
    if match_level:
        sign, num_str = match_level.group(1), match_level.group(2)
        multiplier = -1.0 if sign == "-" else 1.0
        val = multiplier * float(num_str.replace(",", "."))
        return DimensionCandidate(
            raw_text=text,
            dimension_type=DimensionCandidateType.LEVEL_MARK,
            normalized_value=val,
            unit=Unit.M,
            bbox=span.bbox,
            page_number=page_number,
            document_id=document_id,
            warnings=["Architectural level mark relative to ±0,00 datum (meters)."]
        )

    # 4. Explicit units: "120 cm", "2400 mm", "5.00 m"
    match_explicit = RE_EXPLICIT.match(text)
    if match_explicit:
        num_str, unit_str = match_explicit.group(1), match_explicit.group(2).lower()
        val = parse_hungarian_float(num_str)
        unit = Unit.CM if unit_str == "cm" else (Unit.MM if unit_str == "mm" else Unit.M)
        return DimensionCandidate(
            raw_text=text,
            dimension_type=DimensionCandidateType.EXPLICIT_UNIT,
            normalized_value=val,
            unit=unit,
            bbox=span.bbox,
            page_number=page_number,
            document_id=document_id
        )

    # 5. Hungarian decimal notation with 2 decimals (e.g. "5,00", "2,40", "12,85")
    match_dec = RE_DECIMAL_METERS.match(text)
    if match_dec:
        val = parse_hungarian_float(text)
        return DimensionCandidate(
            raw_text=text,
            dimension_type=DimensionCandidateType.LINEAR_DIMENSION,
            normalized_value=val,
            unit=Unit.M,
            bbox=span.bbox,
            page_number=page_number,
            document_id=document_id,
            warnings=["Decimal notation without unit: assumed meters (dimension chain)."]
        )

    # 6. Integer dimension (e.g. "240", "38", "120", "600", "30")
    match_int = RE_INTEGER_CM.match(text)
    if match_int:
        val = float(match_int.group(1))
        # Exclude common sheet/page numbers (1-9) or standard years (1900-2099)
        if 10 <= val <= 1899 or val >= 2100:
            return DimensionCandidate(
                raw_text=text,
                dimension_type=DimensionCandidateType.LINEAR_DIMENSION,
                normalized_value=val,
                unit=Unit.CM,
                bbox=span.bbox,
                page_number=page_number,
                document_id=document_id,
                warnings=["Integer dimension without unit: assumed centimeters."]
            )

    return None


def extract_dimension_candidates(
    text_spans: list[ExtractedTextSpan],
    page_number: int,
    document_id: Optional[UUID] = None
) -> list[DimensionCandidate]:
    """Scan all text spans on a page and extract structured dimension candidates."""
    candidates: list[DimensionCandidate] = []
    for span in text_spans:
        cand = extract_dimension_candidate_from_span(span, page_number, document_id)
        if cand is not None:
            candidates.append(cand)
    return candidates
