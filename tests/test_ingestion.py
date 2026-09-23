"""Unit tests for document ingestion, hashing, revisioning, and immutability."""

from pathlib import Path
from uuid import uuid4
import pytest

from tz_plan_pipeline.core.db import DatabaseManager, ProjectRepository
from tz_plan_pipeline.ingestion import (
    DocumentIngestionService,
    IngestionStatus,
    compute_file_sha256,
    verify_file_sha256,
)
from tz_plan_pipeline.models import Project
from tests.fixtures.pdf_generators import (
    create_corrupted_pdf,
    create_encrypted_pdf,
    create_synthetic_vector_plan_pdf,
)


@pytest.fixture
def ingestion_setup(tmp_path: Path):
    proj_dir = tmp_path / "project_root"
    proj_dir.mkdir(parents=True, exist_ok=True)
    db_file = proj_dir / "project.db"
    db_mgr = DatabaseManager(db_file)
    repo = ProjectRepository(db_mgr)

    project = Project(name="Ingestion Test Project", code="ING-001")
    repo.create_project(project)

    service = DocumentIngestionService(repo, proj_dir)
    return project, service, proj_dir, tmp_path


def test_ingest_single_pdf_success(ingestion_setup):
    project, service, proj_dir, tmp_path = ingestion_setup
    pdf_path = create_synthetic_vector_plan_pdf(tmp_path / "alaprajz.pdf", pages=2)

    original_sha = compute_file_sha256(pdf_path)
    result = service.ingest_file(project.id, pdf_path)

    assert result.status == IngestionStatus.SUCCESS_NEW_DOCUMENT
    assert result.document_id is not None
    assert result.revision_id is not None
    assert result.revision_code == "rev01"
    assert result.file_hash == original_sha
    assert result.page_count == 2

    # Check database records
    docs = service.repo.list_documents(project.id)
    assert len(docs) == 1
    assert docs[0].filename == "alaprajz.pdf"
    assert docs[0].is_immutable is True

    pages = service.repo.get_pages(result.revision_id)
    assert len(pages) == 2
    assert pages[0].page_number == 1
    assert pages[0].geometry.width_pt == pytest.approx(841.89)

    # Check project storage copy
    stored_copy = proj_dir / "documents" / str(result.document_id) / "rev01_alaprajz.pdf"
    assert stored_copy.exists()
    assert verify_file_sha256(stored_copy, original_sha)

    # Verify original source file is still intact and unmodified
    assert verify_file_sha256(pdf_path, original_sha)


def test_ingest_unchanged_duplicate_is_ignored(ingestion_setup):
    project, service, proj_dir, tmp_path = ingestion_setup
    pdf_path = create_synthetic_vector_plan_pdf(tmp_path / "homlokzat.pdf", pages=1)

    # First ingestion
    res1 = service.ingest_file(project.id, pdf_path)
    assert res1.status == IngestionStatus.SUCCESS_NEW_DOCUMENT

    # Attempt re-importing the identical file
    res2 = service.ingest_file(project.id, pdf_path)
    assert res2.status == IngestionStatus.DUPLICATE_IGNORED
    assert res2.document_id == res1.document_id
    assert res2.revision_id == res1.revision_id

    # Verify no second revision was created in DB
    revisions = service.repo.list_revisions(res1.document_id)
    assert len(revisions) == 1


def test_ingest_modified_file_creates_new_revision(ingestion_setup):
    project, service, proj_dir, tmp_path = ingestion_setup
    pdf_path = create_synthetic_vector_plan_pdf(tmp_path / "metszet.pdf", pages=1, include_scale_label="M 1:50")

    # Ingest original rev01
    res1 = service.ingest_file(project.id, pdf_path)
    assert res1.status == IngestionStatus.SUCCESS_NEW_DOCUMENT
    assert res1.revision_code == "rev01"

    # Modify the PDF content (e.g. revised drawing from architect)
    create_synthetic_vector_plan_pdf(pdf_path, pages=1, include_scale_label="M 1:100")
    new_sha = compute_file_sha256(pdf_path)
    assert new_sha != res1.file_hash

    # Ingest modified revision
    res2 = service.ingest_file(project.id, pdf_path)
    assert res2.status == IngestionStatus.SUCCESS_NEW_REVISION
    assert res2.revision_code == "rev02"
    assert res2.document_id == res1.document_id
    assert res2.file_hash == new_sha

    # Verify active/current revision flag
    rev1 = service.repo.get_revision(res1.revision_id)
    rev2 = service.repo.get_revision(res2.revision_id)
    assert rev1.is_current is False
    assert rev2.is_current is True

    # Check both stored files exist in immutable project folder
    stored_v1 = proj_dir / "documents" / str(res1.document_id) / "rev01_metszet.pdf"
    stored_v2 = proj_dir / "documents" / str(res1.document_id) / "rev02_metszet.pdf"
    assert stored_v1.exists()
    assert stored_v2.exists()
    assert verify_file_sha256(stored_v1, res1.file_hash)
    assert verify_file_sha256(stored_v2, new_sha)


def test_ingest_corrupted_pdf_handled_gracefully(ingestion_setup):
    project, service, proj_dir, tmp_path = ingestion_setup
    corrupted_path = create_corrupted_pdf(tmp_path / "broken.pdf")

    res = service.ingest_file(project.id, corrupted_path)
    assert res.status == IngestionStatus.FAILED_CORRUPTED
    assert "Corrupted or invalid" in res.message


def test_ingest_encrypted_pdf_handled_gracefully(ingestion_setup):
    project, service, proj_dir, tmp_path = ingestion_setup
    enc_path = create_encrypted_pdf(tmp_path / "protected.pdf", password="topsecret")

    res = service.ingest_file(project.id, enc_path)
    assert res.status == IngestionStatus.FAILED_ENCRYPTED
    assert "encrypted" in res.message.lower()


def test_ingest_directory_of_pdfs(ingestion_setup):
    project, service, proj_dir, tmp_path = ingestion_setup
    folder = tmp_path / "batch_drawings"
    create_synthetic_vector_plan_pdf(folder / "sheet1.pdf", pages=1)
    create_synthetic_vector_plan_pdf(folder / "sheet2.pdf", pages=2)

    results = service.ingest_directory(project.id, folder)
    assert len(results) == 2
    assert all(r.status == IngestionStatus.SUCCESS_NEW_DOCUMENT for r in results)

    docs = service.repo.list_documents(project.id)
    assert len(docs) == 2


def test_sha256_integrity_failure_on_tampered_stored_file(ingestion_setup):
    """Verify that tampering with stored files is detected by SHA-256 validation."""
    from tz_plan_pipeline.core.errors import DocumentImmutabilityError

    project, service, proj_dir, tmp_path = ingestion_setup
    pdf_path = create_synthetic_vector_plan_pdf(tmp_path / "plan_secure.pdf", pages=1)

    result = service.ingest_file(project.id, pdf_path)
    stored_file = proj_dir / "documents" / str(result.document_id) / f"{result.revision_code}_plan_secure.pdf"

    # Tamper with stored file
    with open(stored_file, "ab") as f:
        f.write(b"malicious append")

    rev = service.repo.get_revision(result.revision_id)
    with open(stored_file, "rb") as f:
        tampered_bytes = f.read()

    with pytest.raises(DocumentImmutabilityError, match="File integrity check failed"):
        rev.verify_file_content(tampered_bytes)


def test_original_document_bytes_immutability(ingestion_setup):
    """Verify that ingestion leaves the external source file 100% byte-for-byte identical."""
    project, service, proj_dir, tmp_path = ingestion_setup
    source_pdf = create_synthetic_vector_plan_pdf(tmp_path / "untouched.pdf", pages=1)

    with open(source_pdf, "rb") as f:
        before_bytes = f.read()

    res = service.ingest_file(project.id, source_pdf)
    assert res.status == IngestionStatus.SUCCESS_NEW_DOCUMENT

    with open(source_pdf, "rb") as f:
        after_bytes = f.read()

    assert before_bytes == after_bytes

