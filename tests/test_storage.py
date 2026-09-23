"""Unit tests for SQLite database management, migrations, and typed repository."""

from pathlib import Path
from uuid import uuid4
import pytest

from tz_plan_pipeline.core.db import DatabaseManager, ProjectRepository
from tz_plan_pipeline.core.errors import StorageError
from tz_plan_pipeline.models import (
    ActorInfo,
    ActorRole,
    AuditFinding,
    BuildingElement,
    ElementType,
    FindingSeverity,
    Measurement,
    Project,
    Quantity,
    QuantityInput,
    ReviewDecision,
    ReviewStatus,
    Unit,
    ValueOrigin,
    VerificationStatus,
)


@pytest.fixture
def repo(tmp_path: Path) -> ProjectRepository:
    db_file = tmp_path / "test_project.db"
    db_manager = DatabaseManager(db_file)
    return ProjectRepository(db_manager)


def test_schema_migration_initialization(repo: ProjectRepository):
    # Verify migration table is populated with version 1
    with repo.db_manager.get_connection() as conn:
        cursor = conn.execute("SELECT version, name FROM schema_migrations;")
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]["version"] == 1
        assert rows[0]["name"] == "001_initial_schema"


def test_create_and_get_project(repo: ProjectRepository):
    proj = Project(name="Nyíregyháza Hőszigetelés", code="TZ-NY-01")
    repo.create_project(proj)

    fetched = repo.get_project(proj.id)
    assert fetched is not None
    assert fetched.name == "Nyíregyháza Hőszigetelés"
    assert fetched.code == "TZ-NY-01"

    by_code = repo.get_project_by_code("TZ-NY-01")
    assert by_code is not None
    assert by_code.id == proj.id


def test_duplicate_project_code_raises_storage_error(repo: ProjectRepository):
    p1 = Project(name="Project A", code="DUP-01")
    p2 = Project(name="Project B", code="DUP-01")
    repo.create_project(p1)

    with pytest.raises(StorageError, match="Could not create project with code 'DUP-01'"):
        repo.create_project(p2)


def test_save_and_retrieve_building_elements(repo: ProjectRepository):
    proj = Project(name="Project C", code="PRJ-C")
    repo.create_project(proj)

    elem = BuildingElement(
        project_id=proj.id,
        stable_key="GF-WALL-01",
        element_type=ElementType.FACADE_WALL,
        identifier="W-01",
        name="Északi homlokzati fal",
        level="Földszint"
    )
    repo.save_building_element(elem)

    elements = repo.get_building_elements(proj.id)
    assert len(elements) == 1
    assert elements[0].stable_key == "GF-WALL-01"
    assert elements[0].name == "Északi homlokzati fal"


def test_save_measurements_and_quantities(repo: ProjectRepository):
    proj = Project(name="Project D", code="PRJ-D")
    repo.create_project(proj)

    elem = BuildingElement(
        project_id=proj.id,
        stable_key="GF-WINDOW-01",
        element_type=ElementType.OPENING_WINDOW,
        identifier="NY-01"
    )
    repo.save_building_element(elem)

    ev_id = uuid4()
    meas = Measurement(
        element_id=elem.id,
        name="width",
        value=1.50,
        unit=Unit.M,
        origin=ValueOrigin.EXTRACTED,
        verification_status=VerificationStatus.UNVERIFIED,
        evidence_ids=[ev_id]
    )
    repo.save_measurement(meas)

    qty = Quantity(
        project_id=proj.id,
        element_id=elem.id,
        name="window_opening_area",
        value=2.25,
        unit=Unit.M2,
        formula_expression="width * height",
        inputs=[
            QuantityInput(
                measurement_id=meas.id,
                measurement_name="width",
                recorded_value=1.50,
                recorded_unit=Unit.M
            )
        ]
    )
    repo.save_quantity(qty)


def test_save_finding_and_review_decision(repo: ProjectRepository):
    proj = Project(name="Project E", code="PRJ-E")
    repo.create_project(proj)

    finding = AuditFinding(
        project_id=proj.id,
        severity=FindingSeverity.WARNING,
        rule_id="RULE-UNVERIFIED-TAKEOFF",
        description="Measurement lacks second verification source."
    )
    repo.save_audit_finding(finding)

    actor = ActorInfo(
        actor_id="usr-123",
        actor_role=ActorRole.HUMAN_REVIEWER,
        actor_name="Nagy Éva Építésvezető"
    )
    decision = ReviewDecision.create_human_approval(
        actor=actor,
        finding_id=finding.id,
        comment="Confirmed with client on site."
    )
    repo.save_review_decision(decision)
