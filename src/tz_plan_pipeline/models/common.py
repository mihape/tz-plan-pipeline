"""Common value objects and domain-level boundary types."""

from typing import Optional
from pydantic import BaseModel, Field, model_validator

from tz_plan_pipeline.models.enums import ActorRole


class BoundingBox(BaseModel):
    """Canonical PDF coordinates bounding box in points (1/72 inch).

    Follows canonical PDF coordinate conventions where x0 <= x1 and y0 <= y1.
    """
    x0: float = Field(description="Minimum X coordinate in points")
    y0: float = Field(description="Minimum Y coordinate in points")
    x1: float = Field(description="Maximum X coordinate in points")
    y1: float = Field(description="Maximum Y coordinate in points")

    @model_validator(mode="after")
    def validate_coordinates(self) -> "BoundingBox":
        if self.x0 > self.x1:
            raise ValueError(f"Invalid BoundingBox: x0 ({self.x0}) cannot be greater than x1 ({self.x1})")
        if self.y0 > self.y1:
            raise ValueError(f"Invalid BoundingBox: y0 ({self.y0}) cannot be greater than y1 ({self.y1})")
        return self

    @property
    def width(self) -> float:
        """Width in points."""
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        """Height in points."""
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        """Area in square points."""
        return self.width * self.height


class Point2D(BaseModel):
    """2D coordinate point."""
    x: float
    y: float


class ActorInfo(BaseModel):
    """Represents an actor in the system as a domain-level approval boundary.

    NOTE: This is a domain-level authorization boundary, not full cryptographic authentication.
    It guarantees that only operations designated as executed by a HUMAN_REVIEWER can authoritatively
    approve review items or overrides. Full identity authentication (tokens, SSO, certificates)
    belongs to the future application/API layer.
    """
    actor_id: str = Field(description="Unique identifier for the user or system component")
    actor_role: ActorRole = Field(description="Role of the actor: HUMAN_REVIEWER, SYSTEM_RULE, or AI_AGENT")
    actor_name: str = Field(description="Human-readable name of the actor")
    organization: Optional[str] = Field(default=None, description="Company or department")

    def can_approve(self) -> bool:
        """Enforces Non-Negotiable Principle 10: User approval must not be simulated by an AI agent.

        Only HUMAN_REVIEWER is authorized to execute authoritative approval decisions.
        """
        return self.actor_role == ActorRole.HUMAN_REVIEWER
