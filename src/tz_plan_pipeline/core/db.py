"""SQLite persistence layer with versioned schema migrations for TZ Plan Pipeline."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

from tz_plan_pipeline.core.errors import StorageError
from tz_plan_pipeline.models import (
    ActorInfo,
    ActorRole,
    AuditFinding,
    BoundingBox,
    BuildingElement,
    CalculationMethod,
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
from tz_plan_pipeline.core.coordinates import PageGeometry, DrawingScale, ScaleStatus, CoordinateOrigin

CURRENT_SCHEMA_VERSION = 1

MIGRATION_V1_SQL = """
-- Version 1: Initial Core Domain Schema

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    code TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    is_immutable INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS document_revisions (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    revision_code TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    source_path TEXT NOT NULL,
    is_current INTEGER NOT NULL DEFAULT 1,
    received_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pages (
    id TEXT PRIMARY KEY,
    revision_id TEXT NOT NULL,
    page_number INTEGER NOT NULL,
    width_pt REAL NOT NULL,
    height_pt REAL NOT NULL,
    rotation INTEGER NOT NULL,
    origin TEXT NOT NULL,
    dpi REAL NOT NULL,
    scale_json TEXT NOT NULL,
    sheet_number TEXT,
    sheet_title TEXT,
    metadata_json TEXT NOT NULL,
    FOREIGN KEY(revision_id) REFERENCES document_revisions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    page_id TEXT NOT NULL,
    x0 REAL NOT NULL,
    y0 REAL NOT NULL,
    x1 REAL NOT NULL,
    y1 REAL NOT NULL,
    source_type TEXT NOT NULL,
    text_content TEXT,
    visual_hash TEXT,
    confidence REAL,
    extraction_timestamp TEXT NOT NULL,
    raw_metadata_json TEXT NOT NULL,
    FOREIGN KEY(page_id) REFERENCES pages(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS building_elements (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    stable_key TEXT NOT NULL,
    element_type TEXT NOT NULL,
    identifier TEXT NOT NULL,
    name TEXT,
    level TEXT,
    room_ref TEXT,
    parent_element_id TEXT,
    metadata_json TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS measurements (
    id TEXT PRIMARY KEY,
    element_id TEXT,
    name TEXT NOT NULL,
    value REAL,
    unit TEXT NOT NULL,
    origin TEXT NOT NULL,
    verification_status TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL,
    replaces_measurement_id TEXT,
    superseded_by_id TEXT,
    confidence REAL,
    notes TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(element_id) REFERENCES building_elements(id) ON DELETE SET NULL,
    FOREIGN KEY(replaces_measurement_id) REFERENCES measurements(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS quantities (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    element_id TEXT,
    name TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    calculation_method TEXT NOT NULL,
    formula_expression TEXT NOT NULL,
    needs_recalculation INTEGER NOT NULL DEFAULT 0,
    calculated_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY(element_id) REFERENCES building_elements(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS quantity_inputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quantity_id TEXT NOT NULL,
    measurement_id TEXT NOT NULL,
    measurement_name TEXT NOT NULL,
    recorded_value REAL NOT NULL,
    recorded_unit TEXT NOT NULL,
    is_valid INTEGER NOT NULL DEFAULT 1,
    invalidation_reason TEXT,
    FOREIGN KEY(quantity_id) REFERENCES quantities(id) ON DELETE CASCADE,
    FOREIGN KEY(measurement_id) REFERENCES measurements(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_findings (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    description TEXT NOT NULL,
    conflicting_evidence_ids_json TEXT NOT NULL,
    conflicting_measurement_ids_json TEXT NOT NULL,
    resolved INTEGER NOT NULL DEFAULT 0,
    resolution_decision_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS review_decisions (
    id TEXT PRIMARY KEY,
    finding_id TEXT,
    status TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    actor_name TEXT NOT NULL,
    organization TEXT,
    comment TEXT NOT NULL,
    override_value REAL,
    override_unit TEXT,
    decided_at TEXT NOT NULL,
    FOREIGN KEY(finding_id) REFERENCES audit_findings(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_elements_stable_key ON building_elements(project_id, stable_key);
CREATE INDEX IF NOT EXISTS idx_measurements_element ON measurements(element_id);
CREATE INDEX IF NOT EXISTS idx_quantities_project ON quantities(project_id);
CREATE INDEX IF NOT EXISTS idx_audit_findings_project ON audit_findings(project_id);
"""


class DatabaseManager:
    """Manages SQLite connections, transactions, and versioned schema migrations."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        """Create a connection configured with WAL mode and foreign keys enabled."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def initialize_schema(self) -> None:
        """Run pending schema migrations."""
        with self.get_connection() as conn:
            # Check current version
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, name TEXT, applied_at TEXT);"
            )
            cursor = conn.execute("SELECT MAX(version) FROM schema_migrations;")
            row = cursor.fetchone()
            current_ver = row[0] if row and row[0] is not None else 0

            if current_ver < 1:
                conn.executescript(MIGRATION_V1_SQL)
                conn.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?);",
                    (1, "001_initial_schema", datetime.now(timezone.utc).isoformat())
                )
            conn.commit()


class ProjectRepository:
    """Repository providing typed storage access for domain models."""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.db_manager.initialize_schema()

    def create_project(self, project: Project) -> Project:
        """Persist a new Project."""
        sql = """
        INSERT INTO projects (id, name, code, description, created_at, updated_at, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """
        with self.db_manager.get_connection() as conn:
            try:
                conn.execute(sql, (
                    str(project.id),
                    project.name,
                    project.code,
                    project.description,
                    project.created_at.isoformat(),
                    project.updated_at.isoformat(),
                    json.dumps(project.metadata)
                ))
                conn.commit()
            except sqlite3.IntegrityError as e:
                raise StorageError(f"Could not create project with code '{project.code}': {e}") from e
        return project

    def get_project(self, project_id: UUID) -> Optional[Project]:
        """Retrieve a Project by its UUID."""
        sql = "SELECT * FROM projects WHERE id = ?;"
        with self.db_manager.get_connection() as conn:
            cursor = conn.execute(sql, (str(project_id),))
            row = cursor.fetchone()
            if not row:
                return None
            return Project(
                id=UUID(row["id"]),
                name=row["name"],
                code=row["code"],
                description=row["description"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                metadata=json.loads(row["metadata_json"])
            )

    def get_project_by_code(self, code: str) -> Optional[Project]:
        """Retrieve a Project by its unique code."""
        sql = "SELECT * FROM projects WHERE code = ?;"
        with self.db_manager.get_connection() as conn:
            cursor = conn.execute(sql, (code,))
            row = cursor.fetchone()
            if not row:
                return None
            return Project(
                id=UUID(row["id"]),
                name=row["name"],
                code=row["code"],
                description=row["description"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                metadata=json.loads(row["metadata_json"])
            )

    def list_projects(self) -> list[Project]:
        """List all projects."""
        sql = "SELECT * FROM projects ORDER BY created_at DESC;"
        with self.db_manager.get_connection() as conn:
            cursor = conn.execute(sql)
            rows = cursor.fetchall()
            return [
                Project(
                    id=UUID(r["id"]),
                    name=r["name"],
                    code=r["code"],
                    description=r["description"],
                    created_at=datetime.fromisoformat(r["created_at"]),
                    updated_at=datetime.fromisoformat(r["updated_at"]),
                    metadata=json.loads(r["metadata_json"])
                )
                for r in rows
            ]

    def save_building_element(self, element: BuildingElement) -> None:
        """Persist or update a BuildingElement."""
        sql = """
        INSERT OR REPLACE INTO building_elements
        (id, project_id, stable_key, element_type, identifier, name, level, room_ref, parent_element_id, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        with self.db_manager.get_connection() as conn:
            conn.execute(sql, (
                str(element.id),
                str(element.project_id),
                element.stable_key,
                element.element_type.value,
                element.identifier,
                element.name,
                element.level,
                element.room_ref,
                str(element.parent_element_id) if element.parent_element_id else None,
                json.dumps(element.metadata)
            ))
            conn.commit()

    def get_building_elements(self, project_id: UUID) -> list[BuildingElement]:
        """Get all BuildingElements for a project."""
        sql = "SELECT * FROM building_elements WHERE project_id = ?;"
        with self.db_manager.get_connection() as conn:
            rows = conn.execute(sql, (str(project_id),)).fetchall()
            return [
                BuildingElement(
                    id=UUID(r["id"]),
                    project_id=UUID(r["project_id"]),
                    stable_key=r["stable_key"],
                    element_type=ElementType(r["element_type"]),
                    identifier=r["identifier"],
                    name=r["name"],
                    level=r["level"],
                    room_ref=r["room_ref"],
                    parent_element_id=UUID(r["parent_element_id"]) if r["parent_element_id"] else None,
                    metadata=json.loads(r["metadata_json"])
                )
                for r in rows
            ]

    def save_measurement(self, measurement: Measurement) -> None:
        """Persist or update a Measurement."""
        sql = """
        INSERT OR REPLACE INTO measurements
        (id, element_id, name, value, unit, origin, verification_status, evidence_ids_json,
         replaces_measurement_id, superseded_by_id, confidence, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        with self.db_manager.get_connection() as conn:
            conn.execute(sql, (
                str(measurement.id),
                str(measurement.element_id) if measurement.element_id else None,
                measurement.name,
                measurement.value,
                measurement.unit.value,
                measurement.origin.value,
                measurement.verification_status.value,
                json.dumps([str(eid) for eid in measurement.evidence_ids]),
                str(measurement.replaces_measurement_id) if measurement.replaces_measurement_id else None,
                str(measurement.superseded_by_id) if measurement.superseded_by_id else None,
                measurement.confidence,
                measurement.notes,
                measurement.created_at.isoformat()
            ))
            conn.commit()

    def save_quantity(self, quantity: Quantity) -> None:
        """Persist a Quantity and its input snapshots."""
        sql_qty = """
        INSERT OR REPLACE INTO quantities
        (id, project_id, element_id, name, value, unit, calculation_method, formula_expression, needs_recalculation, calculated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        sql_input = """
        INSERT INTO quantity_inputs
        (quantity_id, measurement_id, measurement_name, recorded_value, recorded_unit, is_valid, invalidation_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """
        with self.db_manager.get_connection() as conn:
            conn.execute(sql_qty, (
                str(quantity.id),
                str(quantity.project_id),
                str(quantity.element_id) if quantity.element_id else None,
                quantity.name,
                quantity.value,
                quantity.unit.value,
                quantity.calculation_method.value,
                quantity.formula_expression,
                1 if quantity.needs_recalculation else 0,
                quantity.calculated_at.isoformat()
            ))
            conn.execute("DELETE FROM quantity_inputs WHERE quantity_id = ?;", (str(quantity.id),))
            for inp in quantity.inputs:
                conn.execute(sql_input, (
                    str(quantity.id),
                    str(inp.measurement_id),
                    inp.measurement_name,
                    inp.recorded_value,
                    inp.recorded_unit.value,
                    1 if inp.is_valid else 0,
                    inp.invalidation_reason
                ))
            conn.commit()

    def save_audit_finding(self, finding: AuditFinding) -> None:
        """Persist or update an AuditFinding."""
        sql = """
        INSERT OR REPLACE INTO audit_findings
        (id, project_id, severity, rule_id, description, conflicting_evidence_ids_json,
         conflicting_measurement_ids_json, resolved, resolution_decision_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        with self.db_manager.get_connection() as conn:
            conn.execute(sql, (
                str(finding.id),
                str(finding.project_id),
                finding.severity.value,
                finding.rule_id,
                finding.description,
                json.dumps([str(eid) for eid in finding.conflicting_evidence_ids]),
                json.dumps([str(mid) for mid in finding.conflicting_measurement_ids]),
                1 if finding.resolved else 0,
                str(finding.resolution_decision_id) if finding.resolution_decision_id else None,
                finding.created_at.isoformat()
            ))
            conn.commit()

    def save_review_decision(self, decision: ReviewDecision) -> None:
        """Persist an authoritative ReviewDecision."""
        sql = """
        INSERT OR REPLACE INTO review_decisions
        (id, finding_id, status, actor_id, actor_role, actor_name, organization, comment, override_value, override_unit, decided_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        with self.db_manager.get_connection() as conn:
            conn.execute(sql, (
                str(decision.id),
                str(decision.finding_id) if decision.finding_id else None,
                decision.status.value,
                decision.decided_by.actor_id,
                decision.decided_by.actor_role.value,
                decision.decided_by.actor_name,
                decision.decided_by.organization,
                decision.comment,
                decision.override_value,
                decision.override_unit.value if decision.override_unit else None,
                decision.decided_at.isoformat()
            ))
            conn.commit()
