"""Evidence domain model for tracking source lineage and drawing locations."""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

from tz_plan_pipeline.models.common import BoundingBox
from tz_plan_pipeline.models.enums import EvidenceSourceType


class Evidence(BaseModel):
    """Represents an extracted or annotated piece of source evidence from a drawing page.

    Enforces Non-Negotiable Principle 3: Every extracted measurement must retain its
    original source, document revision, page and location.
    Enforces Non-Negotiable Principle 6: The system must not fabricate measurements or references.
    """
    id: UUID = Field(default_factory=uuid4, description="Unique evidence UUID")
    page_id: UUID = Field(description="UUID of the Page containing this evidence")
    bounding_box: BoundingBox = Field(
        description="Canonical PDF bounding box coordinates (pt) of the evidence"
    )
    source_type: EvidenceSourceType = Field(
        description="Extraction method / source type (vector, text, OCR, annotation, AI)"
    )
    text_content: Optional[str] = Field(
        default=None,
        description="Text extracted from this location (e.g. dimension label '240', '150/150')"
    )
    visual_hash: Optional[str] = Field(
        default=None,
        description="Optional perceptual or cryptographic hash of the cropped image region"
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Extraction confidence (0.0 to 1.0). NOTE: Never treated as proof of verification."
    )
    extraction_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when evidence was extracted"
    )
    raw_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Raw technical metadata (e.g. CAD layer name, font, stroke color)"
    )
