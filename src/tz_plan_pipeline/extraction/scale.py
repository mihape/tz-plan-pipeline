"""Scale label candidate extraction, multi-scale drawing regions, and geometric calibration verification."""

import math
import re
from typing import Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

from tz_plan_pipeline.core.coordinates import DrawingScale, ScaleStatus
from tz_plan_pipeline.core.units import PT_TO_M_FACTOR
from tz_plan_pipeline.extraction.dimensions import DimensionCandidate, DimensionCandidateType
from tz_plan_pipeline.extraction.pdf_extractor import ExtractedTextSpan, ExtractedVectorPath, VectorCommandType
from tz_plan_pipeline.models import AuditFinding
from tz_plan_pipeline.models.common import BoundingBox, Point2D
from tz_plan_pipeline.models.enums import FindingSeverity, Unit

RE_SCALE = re.compile(
    r"(?:m(?:éretarány)?\s*[:=]?\s*1\s*[:/]\s*(\d+)|(?:^|\s)1\s*[:/]\s*(\d{2,4})(?:$|\s))",
    re.IGNORECASE
)


class ScaleCandidate(BaseModel):
    """Printed scale label detected on drawing text layer."""
    label: str = Field(description="Raw text snippet containing scale label")
    declared_ratio: float = Field(gt=0, description="Declared denominator (e.g. 50.0 for 1:50)")
    bbox: BoundingBox = Field(description="Bounding box of the scale label")
    page_number: int = Field(ge=1)


class DrawingScaleRegion(BaseModel):
    """Sub-region of a drawing page with an independent scale.

    Enforces that multiple drawings (e.g. detail at 1:20 and floor plan at 1:100) on the same page
    maintain independent scales without silently applying a global scale.
    """
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(description="Region label (e.g. 'Földszinti alaprajz', 'Csomópont 1')")
    bbox: Optional[BoundingBox] = Field(
        default=None,
        description="Bounding box of the drawing region. None represents whole page default."
    )
    scale: DrawingScale = Field(default_factory=DrawingScale)


def extract_scale_candidates(
    text_spans: list[ExtractedTextSpan],
    page_number: int
) -> list[ScaleCandidate]:
    """Search text spans for printed scale declarations (e.g. 'M 1:50', 'Méretarány: 1:100')."""
    candidates: list[ScaleCandidate] = []
    for span in text_spans:
        text = span.text.strip()
        match = RE_SCALE.search(text)
        if match:
            ratio_str = match.group(1) or match.group(2)
            if ratio_str:
                ratio = float(ratio_str)
                # Valid architectural scale ratios typically between 1:1 and 1:10000
                if 1 <= ratio <= 10000:
                    candidates.append(ScaleCandidate(
                        label=text,
                        declared_ratio=ratio,
                        bbox=span.bbox,
                        page_number=page_number
                    ))
    return candidates


def _find_collinear_vector_length(
    cand: DimensionCandidate,
    vector_paths: list[ExtractedVectorPath],
    search_radius_pt: float = 40.0
) -> Optional[float]:
    """Find a vector line segment closely aligned with a dimension text span."""
    cx = (cand.bbox.x0 + cand.bbox.x1) / 2.0
    cy = (cand.bbox.y0 + cand.bbox.y1) / 2.0

    best_length: Optional[float] = None

    for v in vector_paths:
        for item in v.items:
            if item.command_type == VectorCommandType.LINE and len(item.points) >= 2:
                p1, p2 = item.points[0], item.points[1]
                # Distance of midpoint of line to text center
                line_mx = (p1.x + p2.x) / 2.0
                line_my = (p1.y + p2.y) / 2.0
                dist = math.hypot(cx - line_mx, cy - line_my)

                if dist <= search_radius_pt:
                    length_pt = math.hypot(p2.x - p1.x, p2.y - p1.y)
                    if length_pt > 10.0:  # Minimum length threshold
                        if best_length is None or length_pt > best_length:
                            best_length = length_pt

    return best_length


def verify_scale_calibration(
    scale_candidate: ScaleCandidate,
    dimension_candidates: list[DimensionCandidate],
    vector_paths: list[ExtractedVectorPath],
    project_id: UUID,
    tolerance_percent: float = 1.0
) -> tuple[DrawingScale, Optional[AuditFinding]]:
    """Attempt to verify and calibrate a declared scale against dimension evidence.

    Rule: Automatic calibration ONLY succeeds where a dimension and its corresponding
    vector geometry endpoints can be verified within tolerance.
    Otherwise, creates an AuditFinding and leaves the scale uncalibrated.
    """
    declared = DrawingScale(
        status=ScaleStatus.DECLARED,
        declared_ratio=scale_candidate.declared_ratio,
        declared_label=scale_candidate.label,
        tolerance_percent=tolerance_percent
    )

    # Search for dimension candidates in meters or cm with reasonable values
    for dim in dimension_candidates:
        if dim.dimension_type == DimensionCandidateType.LINEAR_DIMENSION:
            target_meters: Optional[float] = None
            if dim.unit == Unit.M:
                target_meters = dim.normalized_value
            elif dim.unit == Unit.CM:
                target_meters = dim.normalized_value / 100.0

            if target_meters and target_meters > 0:
                measured_pt = _find_collinear_vector_length(dim, vector_paths)
                if measured_pt is not None and measured_pt > 0:
                    paper_meters = measured_pt * PT_TO_M_FACTOR
                    calculated_ratio = target_meters / paper_meters
                    diff_pct = (
                        abs(calculated_ratio - scale_candidate.declared_ratio)
                        / scale_candidate.declared_ratio
                        * 100.0
                    )

                    if diff_pct <= tolerance_percent:
                        # Successful empirical calibration!
                        calibrated = declared.calibrate(
                            measured_pt=measured_pt,
                            actual_meters=target_meters,
                            calibrated_by="auto_dimension_cross_check"
                        )
                        return calibrated, None

    # Could not verify with geometry -> create review item and leave uncalibrated
    finding = AuditFinding(
        project_id=project_id,
        severity=FindingSeverity.WARNING,
        rule_id="RULE-SCALE-UNCALIBRATED",
        description=(
            f"Page {scale_candidate.page_number}: Declared scale '{scale_candidate.label}' (1:{scale_candidate.declared_ratio:.0f}) "
            "could not be authoritatively calibrated against vector dimension lines. "
            "Authoritative measurements require verified calibration."
        )
    )
    return declared, finding
