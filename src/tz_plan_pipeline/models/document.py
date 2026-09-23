"""Document, DocumentRevision, and Page domain models."""

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, field_validator

from tz_plan_pipeline.core.coordinates import PageGeometry, DrawingScale
from tz_plan_pipeline.core.errors import DocumentImmutabilityError
from tz_plan_pipeline.models.enums import DocumentType


class Page(BaseModel):
    """Represents a single page / sheet within a document revision."""
    id: UUID = Field(default_factory=uuid4, description="Unique page UUID")
    revision_id: UUID = Field(description="Parent DocumentRevision UUID")
    page_number: int = Field(ge=1, description="1-indexed physical page number in the document")
    geometry: PageGeometry = Field(
        description="Canonical coordinate geometry, page dimensions, rotation, and drawing scale"
    )
    sheet_number: Optional[str] = Field(
        default=None,
        description="Architectural sheet identifier from drawing title block (e.g. 'A-01', 'SZ-03')"
    )
    sheet_title: Optional[str] = Field(
        default=None,
        description="Sheet title (e.g. 'Földszinti alaprajz')"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentRevision(BaseModel):
    """Represents a specific revision of a project drawing document."""
    id: UUID = Field(default_factory=uuid4, description="Unique revision UUID")
    document_id: UUID = Field(description="Parent Document UUID")
    revision_code: str = Field(min_length=1, description="Revision label (e.g. 'rev00', 'rev01', 'A')")
    file_hash: str = Field(
        min_length=64,
        max_length=64,
        description="SHA-256 hash of this revision's file content"
    )
    source_path: str = Field(description="Immutable storage location or relative path")
    is_current: bool = Field(default=True, description="Whether this is the latest active revision")
    received_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when this revision was ingested"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    def verify_file_content(self, content_bytes: bytes) -> bool:
        """Verify that the raw bytes match the recorded immutable SHA-256 hash.

        Raises:
            DocumentImmutabilityError: If content does not match the recorded hash.
        """
        computed_hash = hashlib.sha256(content_bytes).hexdigest()
        if computed_hash != self.file_hash:
            raise DocumentImmutabilityError(
                f"File integrity check failed for revision '{self.revision_code}'. "
                f"Expected hash {self.file_hash}, but found {computed_hash}."
            )
        return True


class Document(BaseModel):
    """Represents an architectural/engineering document set within a project.

    Enforces Non-Negotiable Principle 11: Original project documents must remain immutable.
    """
    id: UUID = Field(default_factory=uuid4, description="Unique document UUID")
    project_id: UUID = Field(description="Parent Project UUID")
    filename: str = Field(min_length=1, description="Original filename")
    doc_type: DocumentType = Field(default=DocumentType.OTHER, description="Category of architectural document")
    is_immutable: bool = Field(default=True, description="Enforces immutable original status")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when document was registered"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("is_immutable")
    @classmethod
    def must_be_immutable(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Document.is_immutable must be True to preserve original document integrity.")
        return v
