"""Project domain model for TZ Plan Pipeline."""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class Project(BaseModel):
    """Represents a construction takeoff project."""
    id: UUID = Field(default_factory=uuid4, description="Unique project UUID")
    name: str = Field(min_length=1, description="Human-readable project name")
    code: str = Field(min_length=1, description="Project code (e.g. 'TZ-2026-001')")
    description: Optional[str] = Field(default=None, description="Detailed project description")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of project creation (UTC)"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of last update (UTC)"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional project metadata (client, location, contractor notes)"
    )
