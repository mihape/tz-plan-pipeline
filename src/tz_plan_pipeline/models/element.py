"""BuildingElement domain model with revision-stable identity."""

from typing import Any, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

from tz_plan_pipeline.models.enums import ElementType


class BuildingElement(BaseModel):
    """Represents a physical or architectural building element (wall, window, door, finish).

    Enforces stable identity across document revisions via `stable_key`.
    When revisions change, the building element identity persists, while measurements
    or evidence can be re-anchored.
    """
    id: UUID = Field(default_factory=uuid4, description="Unique building element UUID")
    project_id: UUID = Field(description="Parent Project UUID")
    stable_key: str = Field(
        min_length=1,
        description="Persistent semantic anchor across document revisions (e.g. 'GF-WINDOW-NY01', 'WALL-NORTH-01')"
    )
    element_type: ElementType = Field(description="Category of the element")
    identifier: str = Field(
        min_length=1,
        description="Architectural designation or callout tag on drawings (e.g. 'NY-01', 'W-04')"
    )
    name: Optional[str] = Field(default=None, description="Human readable name or description")
    level: Optional[str] = Field(
        default=None,
        description="Building level / floor (e.g. 'Pince', 'Földszint', '1. Emelet', 'Tetőtér')"
    )
    room_ref: Optional[str] = Field(
        default=None,
        description="Associated room identifier if applicable (e.g. '101 - Nappali')"
    )
    parent_element_id: Optional[UUID] = Field(
        default=None,
        description="Parent element if nested (e.g. window hosted inside a facade wall)"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)
