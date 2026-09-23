"""Measurement domain model with strict provenance, multi-evidence support, and verification lifecycle."""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, model_validator

from tz_plan_pipeline.core.errors import MissingDataError, ProvenanceError
from tz_plan_pipeline.models.enums import Unit, ValueOrigin, VerificationStatus


class Measurement(BaseModel):
    """Represents a measured dimension, area, or count associated with a building element.

    Enforces Non-Negotiable Principles:
    - Principle 3: Every extracted measurement retains its original source references.
    - Principle 4: Extracted, inferred, manual, manually corrected, and AI values are distinguishable.
    - Principle 5: Missing data (None) must never silently become zero (0.0).
    - Principle 6: The system must not fabricate measurements.
    - Provenance rule: A measurement cannot be verified without supporting evidence references.
    """
    id: UUID = Field(default_factory=uuid4, description="Unique measurement UUID")
    element_id: Optional[UUID] = Field(default=None, description="Associated BuildingElement UUID")
    name: str = Field(min_length=1, description="Property name (e.g. 'nominal_width', 'gross_height', 'area')")
    value: Optional[float] = Field(
        default=None,
        description="Measured value. None represents missing data. 0.0 and negative numbers are preserved if valid."
    )
    unit: Unit = Field(description="Measurement physical unit")
    origin: ValueOrigin = Field(
        description="Origin of value (EXTRACTED, INFERRED, MANUAL_INPUT, MANUALLY_CORRECTED, AI_HYPOTHESIS)"
    )
    verification_status: VerificationStatus = Field(
        default=VerificationStatus.UNVERIFIED,
        description="Verification lifecycle status, strictly separated from origin."
    )
    evidence_ids: list[UUID] = Field(
        default_factory=list,
        description="List of supporting Evidence UUIDs across pages or document revisions"
    )
    replaces_measurement_id: Optional[UUID] = Field(
        default=None,
        description="If MANUALLY_CORRECTED, UUID of the original measurement that this replaces"
    )
    superseded_by_id: Optional[UUID] = Field(
        default=None,
        description="If this measurement was corrected or superseded, UUID of the active replacement"
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Extraction confidence. NOTE: Never treated as proof of verification."
    )
    notes: Optional[str] = Field(default=None, description="Contextual notes or commentary")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Creation timestamp (UTC)"
    )

    @model_validator(mode="after")
    def validate_provenance_and_verification(self) -> "Measurement":
        # Rule: A verified measurement must have at least one supporting evidence reference
        # (or for manual input, an explicit audit trail)
        if self.verification_status in (VerificationStatus.AUTO_VERIFIED, VerificationStatus.HUMAN_APPROVED):
            if not self.evidence_ids and self.origin not in (ValueOrigin.MANUAL_INPUT, ValueOrigin.MANUALLY_CORRECTED):
                raise ProvenanceError(
                    f"Measurement '{self.name}' cannot be marked as '{self.verification_status}' "
                    "without supporting evidence references. Unbacked claims cannot be verified."
                )

        # Rule: MANUALLY_CORRECTED must identify the measurement it replaces
        if self.origin == ValueOrigin.MANUALLY_CORRECTED:
            if self.replaces_measurement_id is None:
                raise ProvenanceError(
                    f"Measurement '{self.name}' with origin MANUALLY_CORRECTED must specify 'replaces_measurement_id' "
                    "to preserve audit lineage with the original measurement."
                )

        return self

    def get_required_value(self) -> float:
        """Return the measurement value or raise MissingDataError if missing (None).

        Enforces Non-Negotiable Principle 5: Missing data must never silently become zero.
        """
        if self.value is None:
            raise MissingDataError(
                f"Required measurement '{self.name}' has no value (missing data). "
                "Missing data must never silently become zero."
            )
        return self.value

    def is_superseded(self) -> bool:
        """Return True if this measurement has been superseded by a manual correction."""
        return self.superseded_by_id is not None

    def create_manual_correction(
        self,
        new_value: float,
        notes: str,
        evidence_ids: Optional[list[UUID]] = None
    ) -> "Measurement":
        """Factory method to create a replacement measurement preserving lineage.

        Returns the new measurement and marks this measurement as superseded.
        """
        new_id = uuid4()
        self.superseded_by_id = new_id

        # Retain original evidence references if not overridden
        ev_ids = evidence_ids if evidence_ids is not None else list(self.evidence_ids)

        return Measurement(
            id=new_id,
            element_id=self.element_id,
            name=self.name,
            value=new_value,
            unit=self.unit,
            origin=ValueOrigin.MANUALLY_CORRECTED,
            verification_status=VerificationStatus.REVIEW_REQUIRED,
            evidence_ids=ev_ids,
            replaces_measurement_id=self.id,
            notes=notes
        )
