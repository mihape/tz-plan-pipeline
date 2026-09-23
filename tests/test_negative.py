"""Comprehensive negative and edge-case tests enforcing architectural principles and safety boundaries."""

import hashlib
from uuid import uuid4
import pytest
from pydantic import ValidationError

from tz_plan_pipeline.core.coordinates import (
    CoordinateOrigin,
    DrawingScale,
    PageGeometry,
    ScaleStatus,
    pt_to_real_world_meters,
)
from tz_plan_pipeline.core.errors import (
    ApprovalSimulationError,
    ConflictingEvidenceError,
    DocumentImmutabilityError,
    MissingDataError,
    ProvenanceError,
    ScaleCalibrationError,
    UncalibratedScaleError,
    UnitConversionError,
)
from tz_plan_pipeline.core.units import convert_units
from tz_plan_pipeline.models import (
    ActorInfo,
    ActorRole,
    AuditFinding,
    BoundingBox,
    BuildingElement,
    Document,
    DocumentRevision,
    ElementType,
    Evidence,
    EvidenceSourceType,
    FindingSeverity,
    Measurement,
    Page,
    Project,
    Quantity,
    ReviewDecision,
    ReviewStatus,
    Unit,
    ValueOrigin,
    VerificationStatus,
)


class TestNegativePrinciples:
    """Tests enforcing the 12 Non-Negotiable Principles under failure/invalid conditions."""

    def test_missing_data_never_silently_becomes_zero(self):
        """Principle 5: Missing data must never silently become zero."""
        m_missing = Measurement(
            name="opening_height",
            value=None,
            unit=Unit.M,
            origin=ValueOrigin.EXTRACTED,
            verification_status=VerificationStatus.UNVERIFIED
        )
        # Calling get_required_value on None MUST raise MissingDataError
        with pytest.raises(MissingDataError, match="Missing data must never silently become zero"):
            m_missing.get_required_value()

        # Legitimate 0.0 must NOT raise error
        m_zero = Measurement(
            name="sill_height",
            value=0.0,
            unit=Unit.M,
            origin=ValueOrigin.EXTRACTED,
            verification_status=VerificationStatus.UNVERIFIED
        )
        assert m_zero.get_required_value() == 0.0

    def test_unauthorized_approval_attempt_by_ai_agent_fails(self):
        """Principle 10: User approval must not be simulated by an AI agent."""
        ai_actor = ActorInfo(
            actor_id="claude-3-opus",
            actor_role=ActorRole.AI_AGENT,
            actor_name="AI Autonomous Reviewer"
        )
        assert not ai_actor.can_approve()

        with pytest.raises(ApprovalSimulationError, match="User approval must not be simulated by an AI agent"):
            ReviewDecision.create_human_approval(
                actor=ai_actor,
                finding_id=uuid4(),
                comment="Automated approval attempt"
            )

    def test_unauthorized_approval_attempt_by_system_rule_fails(self):
        """Principle 10: System rules cannot simulate human approval."""
        rule_actor = ActorInfo(
            actor_id="rule-auto-deduct",
            actor_role=ActorRole.SYSTEM_RULE,
            actor_name="Automated Deductions Engine"
        )
        assert not rule_actor.can_approve()

        with pytest.raises(ApprovalSimulationError, match="User approval must not be simulated"):
            ReviewDecision.create_human_approval(
                actor=rule_actor,
                finding_id=uuid4(),
                comment="Automated rule approval"
            )

    def test_verification_status_requires_evidence_lineage(self):
        """Principle 3 & Refinement 4: Cannot be verified without supporting evidence."""
        # Unbacked AUTO_VERIFIED attempt
        with pytest.raises(ProvenanceError, match="cannot be marked as 'auto_verified' without supporting evidence"):
            Measurement(
                name="room_width",
                value=4.50,
                unit=Unit.M,
                origin=ValueOrigin.EXTRACTED,
                verification_status=VerificationStatus.AUTO_VERIFIED,
                evidence_ids=[]
            )

        # Unbacked HUMAN_APPROVED attempt
        with pytest.raises(ProvenanceError, match="cannot be marked as 'human_approved' without supporting evidence"):
            Measurement(
                name="room_width",
                value=4.50,
                unit=Unit.M,
                origin=ValueOrigin.EXTRACTED,
                verification_status=VerificationStatus.HUMAN_APPROVED,
                evidence_ids=[]
            )

    def test_manually_corrected_requires_replaced_measurement_id(self):
        """Refinement 1: MANUALLY_CORRECTED must link to the original measurement it replaces."""
        with pytest.raises(ProvenanceError, match="must specify 'replaces_measurement_id'"):
            Measurement(
                name="wall_thickness",
                value=0.38,
                unit=Unit.M,
                origin=ValueOrigin.MANUALLY_CORRECTED,
                verification_status=VerificationStatus.REVIEW_REQUIRED,
                replaces_measurement_id=None
            )

    def test_document_tamper_fails_immutability_check(self):
        """Principle 11: Original project documents must remain immutable."""
        original_bytes = b"%PDF-1.7 Synthetic test plan contents"
        sha = hashlib.sha256(original_bytes).hexdigest()

        rev = DocumentRevision(
            document_id=uuid4(),
            revision_code="rev00",
            file_hash=sha,
            source_path="plans/ground_floor.pdf"
        )
        assert rev.verify_file_content(original_bytes) is True

        tampered_bytes = b"%PDF-1.7 Maliciously modified plan contents"
        with pytest.raises(DocumentImmutabilityError, match="File integrity check failed"):
            rev.verify_file_content(tampered_bytes)

    def test_document_immutability_flag_cannot_be_disabled(self):
        """Principle 11: Document model prohibits is_immutable=False."""
        with pytest.raises(ValidationError, match="must be True to preserve original document integrity"):
            Document(
                project_id=uuid4(),
                filename="test.pdf",
                is_immutable=False
            )

    def test_conflicting_evidence_preserves_both_sources_without_picking_winner(self):
        """Principle 7 & Refinement 4: Conflicting sources create a review item and preserve both."""
        ev_arch = uuid4()
        ev_spec = uuid4()
        meas_arch = uuid4()
        meas_spec = uuid4()

        # Both conflicting references are preserved in AuditFinding
        finding = AuditFinding(
            project_id=uuid4(),
            severity=FindingSeverity.CONFLICT,
            rule_id="RULE-CROSS-DOC-DISCREPANCY",
            description="Window NY-02 width is 120cm on floor plan A-01, but 125cm in spec schedule K-02",
            conflicting_evidence_ids=[ev_arch, ev_spec],
            conflicting_measurement_ids=[meas_arch, meas_spec]
        )
        assert not finding.resolved
        assert set(finding.conflicting_evidence_ids) == {ev_arch, ev_spec}
        assert set(finding.conflicting_measurement_ids) == {meas_arch, meas_spec}

    def test_uncalibrated_scale_fails_authoritative_conversion(self):
        """Refinement 2: Printed scale label must not produce authoritative real-world measurements."""
        declared_scale = DrawingScale(
            status=ScaleStatus.DECLARED,
            declared_ratio=50.0,
            declared_label="M=1:50"
        )
        assert not declared_scale.is_authoritative()

        with pytest.raises(UncalibratedScaleError, match="Printed scale labels .* must be calibrated"):
            pt_to_real_world_meters(100.0, declared_scale, require_authoritative=True)

        failed_scale = DrawingScale(
            status=ScaleStatus.FAILED_CALIBRATION,
            declared_ratio=50.0,
            calibrated_ratio=65.2
        )
        with pytest.raises(UncalibratedScaleError):
            pt_to_real_world_meters(100.0, failed_scale, require_authoritative=True)

    def test_bounding_box_coordinate_order_validation(self):
        """BoundingBox coordinate order validation: x0 <= x1 and y0 <= y1."""
        with pytest.raises(ValueError, match="x0 .* cannot be greater than x1"):
            BoundingBox(x0=200.0, y0=50.0, x1=100.0, y1=150.0)

        with pytest.raises(ValueError, match="y0 .* cannot be greater than y1"):
            BoundingBox(x0=50.0, y0=250.0, x1=100.0, y1=150.0)

    def test_invalid_unit_conversion_dimensions(self):
        """Cross-dimensional conversion fails."""
        with pytest.raises(UnitConversionError, match="Incompatible unit conversion"):
            convert_units(5.0, "m2", "m3")

        with pytest.raises(UnitConversionError, match="Incompatible unit conversion"):
            convert_units(10.0, "kg", "m")
