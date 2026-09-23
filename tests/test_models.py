"""Unit tests for the 10 core domain models, validation rules, and safety boundaries."""

import hashlib
from uuid import uuid4
import pytest
from pydantic import ValidationError

from tz_plan_pipeline.core.coordinates import DrawingScale, PageGeometry, ScaleStatus
from tz_plan_pipeline.core.errors import (
    ApprovalSimulationError,
    DocumentImmutabilityError,
    MissingDataError,
    ProvenanceError,
)
from tz_plan_pipeline.models import (
    ActorInfo,
    ActorRole,
    AuditFinding,
    BoundingBox,
    BuildingElement,
    Document,
    DocumentRevision,
    DocumentType,
    ElementType,
    Evidence,
    EvidenceSourceType,
    FindingSeverity,
    Measurement,
    Page,
    Project,
    Quantity,
    QuantityInput,
    ReviewDecision,
    ReviewStatus,
    Unit,
    ValueOrigin,
    VerificationStatus,
)


class TestProjectModel:
    def test_project_creation_and_defaults(self):
        project = Project(name="Családi ház Nyíregyháza", code="TZ-2026-001")
        assert project.id is not None
        assert project.name == "Családi ház Nyíregyháza"
        assert project.code == "TZ-2026-001"
        assert project.created_at is not None
        assert project.updated_at is not None


class TestDocumentModels:
    def test_document_and_revision_integrity(self):
        project_id = uuid4()
        doc = Document(
            project_id=project_id,
            filename="alaprajz_v1.pdf",
            doc_type=DocumentType.ARCHITECTURAL_PLAN
        )
        assert doc.is_immutable is True

        content = b"Mock PDF binary content for testing"
        file_hash = hashlib.sha256(content).hexdigest()

        rev = DocumentRevision(
            document_id=doc.id,
            revision_code="rev01",
            file_hash=file_hash,
            source_path="raw_docs/alaprajz_v1.pdf"
        )
        assert rev.verify_file_content(content) is True

        with pytest.raises(DocumentImmutabilityError, match="File integrity check failed"):
            rev.verify_file_content(b"Tampered content")

    def test_page_creation(self):
        rev_id = uuid4()
        geom = PageGeometry(
            width_pt=841.89,
            height_pt=595.28,
            rotation=0,
            scale=DrawingScale(status=ScaleStatus.DECLARED, declared_ratio=50.0)
        )
        page = Page(
            revision_id=rev_id,
            page_number=1,
            geometry=geom,
            sheet_number="A-01",
            sheet_title="Földszint"
        )
        assert page.page_number == 1
        assert page.geometry.width_pt == 841.89


class TestEvidenceModel:
    def test_evidence_provenance_retention(self):
        page_id = uuid4()
        bbox = BoundingBox(x0=100.0, y0=150.0, x1=200.0, y1=250.0)
        evidence = Evidence(
            page_id=page_id,
            bounding_box=bbox,
            source_type=EvidenceSourceType.CAD_TEXT,
            text_content="150 / 150",
            confidence=0.98
        )
        assert evidence.page_id == page_id
        assert evidence.bounding_box.width == 100.0
        assert evidence.bounding_box.height == 100.0
        assert evidence.text_content == "150 / 150"


class TestBuildingElementModel:
    def test_building_element_stable_key(self):
        proj_id = uuid4()
        element = BuildingElement(
            project_id=proj_id,
            stable_key="GF-WINDOW-NY01",
            element_type=ElementType.OPENING_WINDOW,
            identifier="NY-01",
            level="Földszint"
        )
        assert element.stable_key == "GF-WINDOW-NY01"
        assert element.element_type == ElementType.OPENING_WINDOW


class TestMeasurementModel:
    def test_missing_data_vs_legitimate_zero(self):
        # Missing value (None)
        missing_m = Measurement(
            name="offset_distance",
            value=None,
            unit=Unit.M,
            origin=ValueOrigin.EXTRACTED,
            verification_status=VerificationStatus.UNVERIFIED
        )
        assert missing_m.value is None
        with pytest.raises(MissingDataError, match="Missing data must never silently become zero"):
            missing_m.get_required_value()

        # Legitimate 0.0 (e.g. ground level reference offset)
        zero_m = Measurement(
            name="level_delta",
            value=0.0,
            unit=Unit.M,
            origin=ValueOrigin.EXTRACTED,
            verification_status=VerificationStatus.UNVERIFIED
        )
        assert zero_m.value == 0.0
        assert zero_m.get_required_value() == 0.0

        # Legitimate negative value (e.g. basement offset)
        neg_m = Measurement(
            name="basement_level",
            value=-2.80,
            unit=Unit.M,
            origin=ValueOrigin.EXTRACTED,
            verification_status=VerificationStatus.UNVERIFIED
        )
        assert neg_m.get_required_value() == -2.80

    def test_multiple_evidence_support(self):
        ev1 = uuid4()
        ev2 = uuid4()
        m = Measurement(
            name="window_width",
            value=1.50,
            unit=Unit.M,
            origin=ValueOrigin.EXTRACTED,
            verification_status=VerificationStatus.UNVERIFIED,
            evidence_ids=[ev1, ev2]
        )
        assert len(m.evidence_ids) == 2
        assert ev1 in m.evidence_ids
        assert ev2 in m.evidence_ids

    def test_verification_requires_evidence_lineage(self):
        # Attempting to mark unbacked measurement as AUTO_VERIFIED must fail
        with pytest.raises(ProvenanceError, match="cannot be marked as 'auto_verified' without supporting evidence"):
            Measurement(
                name="window_width",
                value=1.50,
                unit=Unit.M,
                origin=ValueOrigin.EXTRACTED,
                verification_status=VerificationStatus.AUTO_VERIFIED,
                evidence_ids=[]  # Missing evidence!
            )

    def test_manually_corrected_preserves_relationship(self):
        ev_id = uuid4()
        original = Measurement(
            name="plinth_height",
            value=0.30,
            unit=Unit.M,
            origin=ValueOrigin.EXTRACTED,
            verification_status=VerificationStatus.UNVERIFIED,
            evidence_ids=[ev_id]
        )
        assert not original.is_superseded()

        # Create manual correction
        corrected = original.create_manual_correction(
            new_value=0.45,
            notes="Corrected based on site inspection report"
        )

        assert original.is_superseded()
        assert original.superseded_by_id == corrected.id
        assert corrected.origin == ValueOrigin.MANUALLY_CORRECTED
        assert corrected.replaces_measurement_id == original.id
        assert corrected.value == 0.45
        assert ev_id in corrected.evidence_ids


class TestQuantityModel:
    def test_quantity_with_input_snapshots(self):
        proj_id = uuid4()
        m1_id = uuid4()
        m2_id = uuid4()

        q = Quantity(
            project_id=proj_id,
            name="gross_facade_area",
            value=150.0,
            unit=Unit.M2,
            formula_expression="facade_length * facade_height",
            inputs=[
                QuantityInput(
                    measurement_id=m1_id,
                    measurement_name="facade_length",
                    recorded_value=15.0,
                    recorded_unit=Unit.M
                ),
                QuantityInput(
                    measurement_id=m2_id,
                    measurement_name="facade_height",
                    recorded_value=10.0,
                    recorded_unit=Unit.M
                )
            ]
        )
        assert q.value == 150.0
        assert len(q.inputs) == 2
        assert not q.needs_recalculation

        q.mark_for_recalculation("Input measurement modified")
        assert q.needs_recalculation is True


class TestAuditAndApprovalBoundary:
    def test_conflicting_evidence_preserved_in_audit_finding(self):
        proj_id = uuid4()
        ev_plan = uuid4()
        ev_schedule = uuid4()
        m_plan = uuid4()
        m_schedule = uuid4()

        finding = AuditFinding(
            project_id=proj_id,
            severity=FindingSeverity.CONFLICT,
            rule_id="RULE-DIM-CROSS-CHECK",
            description="Width on floor plan (150 cm) conflicts with window schedule (140 cm)",
            conflicting_evidence_ids=[ev_plan, ev_schedule],
            conflicting_measurement_ids=[m_plan, m_schedule]
        )
        assert not finding.resolved
        assert len(finding.conflicting_evidence_ids) == 2
        assert len(finding.conflicting_measurement_ids) == 2

    def test_human_approval_succeeds(self):
        human_reviewer = ActorInfo(
            actor_id="user-001",
            actor_role=ActorRole.HUMAN_REVIEWER,
            actor_name="Kovács János Vezető Építész",
            organization="TZ Construction Kft."
        )
        assert human_reviewer.can_approve() is True

        decision = ReviewDecision.create_human_approval(
            actor=human_reviewer,
            finding_id=uuid4(),
            comment="Verified on site: nominal width is 150 cm",
            override_value=1.50,
            override_unit=Unit.M
        )
        assert decision.status == ReviewStatus.APPROVED
        assert decision.decided_by.actor_id == "user-001"
        assert decision.override_value == 1.50

    def test_ai_agent_simulating_approval_raises_error(self):
        ai_agent = ActorInfo(
            actor_id="agent-claude-takeoff",
            actor_role=ActorRole.AI_AGENT,
            actor_name="Takeoff Subagent"
        )
        assert ai_agent.can_approve() is False

        with pytest.raises(ApprovalSimulationError, match="User approval must not be simulated"):
            ReviewDecision.create_human_approval(
                actor=ai_agent,
                finding_id=uuid4(),
                comment="Automated auto-approval by AI agent"
            )
