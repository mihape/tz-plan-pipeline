"""PDF Extraction package for TZ Plan Pipeline."""

from tz_plan_pipeline.extraction.diagnostic import (
    DiagnosticOverlayRenderer,
    ExtractionReport,
    PageReportSummary,
)
from tz_plan_pipeline.extraction.dimensions import (
    DimensionCandidate,
    DimensionCandidateType,
    extract_dimension_candidate_from_span,
    extract_dimension_candidates,
)
from tz_plan_pipeline.extraction.inventory import (
    PageContentClass,
    PageInventory,
    classify_page_content,
    inspect_page_inventory,
)
from tz_plan_pipeline.extraction.pdf_extractor import (
    ExtractedImage,
    ExtractedTextSpan,
    ExtractedVectorPath,
    PageExtractionResult,
    VectorCommand,
    VectorCommandType,
    extract_page_content,
)
from tz_plan_pipeline.extraction.scale import (
    DrawingScaleRegion,
    ScaleCandidate,
    extract_scale_candidates,
    verify_scale_calibration,
)

__all__ = [
    "DiagnosticOverlayRenderer",
    "DimensionCandidate",
    "DimensionCandidateType",
    "DrawingScaleRegion",
    "ExtractedImage",
    "ExtractedTextSpan",
    "ExtractedVectorPath",
    "ExtractionReport",
    "PageContentClass",
    "PageExtractionResult",
    "PageInventory",
    "PageReportSummary",
    "ScaleCandidate",
    "VectorCommand",
    "VectorCommandType",
    "classify_page_content",
    "extract_dimension_candidate_from_span",
    "extract_dimension_candidates",
    "extract_page_content",
    "extract_scale_candidates",
    "inspect_page_inventory",
    "verify_scale_calibration",
]
