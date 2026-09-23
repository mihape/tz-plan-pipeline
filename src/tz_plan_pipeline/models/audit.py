"""AuditFinding and ReviewDecision domain models enforcing the human approval boundary."""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

from tz_plan_pipeline.core.errors import ApprovalSimulationError
from tz_plan_pipeline.models.common import ActorInfo
from tz_plan_pipeline.models.enums import FindingSeverity, ReviewStatus, Unit


class ReviewDecision(BaseModel):
    """Authoritative review decision resolving an audit finding or overriding a measurement.

    Enforces Non-Negotiable Principle 10: User approval must not be simulated by an AI agent.
    Domain-level boundary: only HUMAN_REVIEWER can execute authoritative approvals.
    """
    id: UUID = Field(default_factory=uuid4, description="Unique decision UUID")
    finding_id: Optional[UUID] = Field(default=None, description="Associated AuditFinding UUID, if any")
    status: ReviewStatus = Field(description="Decision outcome (APPROVED, REJECTED, MODIFIED)")
    decided_by: ActorInfo = Field(description="Actor executing the review operation")
    comment: str = Field(min_length=1, description="Mandatory review commentary or justification")
    override_value: Optional[float] = Field(
        default=None,
        description="Optional manual override value selected by reviewer"
    )
    override_unit: Optional[Unit] = Field(default=None, description="Optional override unit")
    decided_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when decision was committed (UTC)"
    )

    @classmethod
    def create_human_approval(
        cls,
        actor: ActorInfo,
        finding_id: Optional[UUID],
        comment: str,
        override_value: Optional[float] = None,
        override_unit: Optional[Unit] = None
    ) -> "ReviewDecision":
        """Factory method enforcing the domain approval boundary.

        Raises:
            ApprovalSimulationError: If actor.actor_role is not HUMAN_REVIEWER.
        """
        if not actor.can_approve():
            raise ApprovalSimulationError(
                f"Actor '{actor.actor_name}' with role '{actor.actor_role}' is not authorized to execute approvals. "
                "Non-Negotiable Principle 10: User approval must not be simulated by an AI agent or automated rule."
            )

        return cls(
            finding_id=finding_id,
            status=ReviewStatus.APPROVED,
            decided_by=actor,
            comment=comment,
            override_value=override_value,
            override_unit=override_unit
        )


class AuditFinding(BaseModel):
    """Represents an issue, geometric discrepancy, or conflict requiring human review.

    Enforces Non-Negotiable Principle 7: Conflicting source data must create a review item.
    Preserves all conflicting source evidence without prematurely choosing a winner.
    """
    id: UUID = Field(default_factory=uuid4, description="Unique finding UUID")
    project_id: UUID = Field(description="Parent Project UUID")
    severity: FindingSeverity = Field(
        description="Severity classification (INFO, WARNING, ERROR, CONFLICT)"
    )
    rule_id: str = Field(min_length=1, description="Rule or check identifier that triggered the finding")
    description: str = Field(min_length=1, description="Detailed explanation of the issue or discrepancy")
    conflicting_evidence_ids: list[UUID] = Field(
        default_factory=list,
        description="All conflicting evidence IDs preserved for human reviewer inspection"
    )
    conflicting_measurement_ids: list[UUID] = Field(
        default_factory=list,
        description="All conflicting measurement IDs preserved without overwriting"
    )
    resolved: bool = Field(default=False, description="Whether finding has been resolved by a review decision")
    resolution_decision_id: Optional[UUID] = Field(
        default=None,
        description="UUID of the ReviewDecision resolving this finding"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Creation timestamp (UTC)"
    )

    def resolve(self, decision: ReviewDecision) -> None:
        """Resolve this finding with an authoritative ReviewDecision."""
        self.resolved = True
        self.resolution_decision_id = decision.id
