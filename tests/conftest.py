"""Shared pytest fixtures and synthetic data generators for TZ Plan Pipeline tests."""

import hashlib
from pathlib import Path
from uuid import uuid4
import pytest

from tz_plan_pipeline.core.coordinates import CoordinateOrigin, DrawingScale, PageGeometry, ScaleStatus
from tz_plan_pipeline.core.db import DatabaseManager, ProjectRepository
from tz_plan_pipeline.models import (
    ActorInfo,
    ActorRole,
    BoundingBox,
    BuildingElement,
    Document,
    DocumentRevision,
    DocumentType,
    ElementType,
    Evidence,
    EvidenceSourceType,
    Measurement,
    Page,
    Project,
    Unit,
    ValueOrigin,
    VerificationStatus,
)


@pytest.fixture
def temp_project_repo(tmp_path: Path) -> ProjectRepository:
    """Fixture providing an isolated ProjectRepository in a temporary directory."""
    db_file = tmp_path / "test_pipeline.db"
    db_mgr = DatabaseManager(db_file)
    return ProjectRepository(db_mgr)


@pytest.fixture
def sample_project() -> Project:
    """Fixture providing a synthetic Project instance."""
    return Project(
        name="Teszt Családi Ház Debrecen",
        code="TZ-TEST-DEB-01",
        description="Szintetikus teszt projekt egységtesztekhez",
        metadata={"region": "Hajdú-Bihar", "contractor": "TZ Kft."}
    )


@pytest.fixture
def synthetic_calibrated_page() -> Page:
    """Fixture providing a synthetic Page with an authoritatively calibrated 1:50 scale."""
    geom = PageGeometry(
        width_pt=841.89,  # A4 Landscape width
        height_pt=595.28, # A4 Landscape height
        rotation=0,
        origin=CoordinateOrigin.TOP_LEFT,
        dpi=72.0,
        scale=DrawingScale(
            status=ScaleStatus.CALIBRATED,
            declared_ratio=50.0,
            declared_label="M=1:50",
            calibrated_ratio=50.0,
            calibrated_by="test_harness"
        )
    )
    return Page(
        revision_id=uuid4(),
        page_number=1,
        geometry=geom,
        sheet_number="A-01",
        sheet_title="Földszinti alaprajz"
    )


@pytest.fixture
def human_reviewer_actor() -> ActorInfo:
    """Fixture providing an authorized human reviewer actor."""
    return ActorInfo(
        actor_id="user-chief-estimator",
        actor_role=ActorRole.HUMAN_REVIEWER,
        actor_name="Szabó Péter Főmérnök",
        organization="TZ Kivitelező Kft."
    )
