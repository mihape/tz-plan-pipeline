"""Document ingestion service for immutable PDF registration and revision tracking."""

from enum import StrEnum
import logging
from pathlib import Path
import shutil
from typing import Optional
from uuid import UUID, uuid4
import pymupdf
from pydantic import BaseModel, Field

from tz_plan_pipeline.core.coordinates import CoordinateOrigin, DrawingScale, PageGeometry, ScaleStatus
from tz_plan_pipeline.core.db import ProjectRepository
from tz_plan_pipeline.core.errors import (
    CorruptedPDFError,
    DocumentImmutabilityError,
    DuplicateDocumentError,
    EncryptedPDFError,
)
from tz_plan_pipeline.ingestion.hasher import compute_file_sha256, verify_file_sha256
from tz_plan_pipeline.models import Document, DocumentRevision, DocumentType, Page

logger = logging.getLogger("tz_plan_pipeline.ingestion")


class IngestionStatus(StrEnum):
    """Result status of a document ingestion attempt."""
    SUCCESS_NEW_DOCUMENT = "success_new_document"
    SUCCESS_NEW_REVISION = "success_new_revision"
    DUPLICATE_IGNORED = "duplicate_ignored"
    FAILED_CORRUPTED = "failed_corrupted"
    FAILED_ENCRYPTED = "failed_encrypted"
    FAILED_NOT_FOUND = "failed_not_found"


class IngestionResult(BaseModel):
    """Structured report of an ingestion operation."""
    status: IngestionStatus
    filename: str
    source_path: str
    document_id: Optional[UUID] = None
    revision_id: Optional[UUID] = None
    revision_code: Optional[str] = None
    file_hash: Optional[str] = None
    page_count: int = 0
    message: str


class DocumentIngestionService:
    """Orchestrates immutable PDF ingestion, validation, hashing, and database storage."""

    def __init__(self, repo: ProjectRepository, project_dir: Path):
        self.repo = repo
        self.project_dir = Path(project_dir)
        self.storage_dir = self.project_dir / "documents"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def ingest_file(
        self,
        project_id: UUID,
        file_path: Path,
        doc_type: DocumentType = DocumentType.ARCHITECTURAL_PLAN
    ) -> IngestionResult:
        """Ingest a single PDF file into a project.

        Enforces:
        - Immutability: copies original into project store and validates SHA-256.
        - Duplicate prevention: rejects unchanged duplicate re-import.
        - Revision management: creates new revision if content changes for existing filename.
        - Graceful error handling for encrypted or corrupted PDFs.
        """
        source_path = Path(file_path)
        if not source_path.is_file():
            return IngestionResult(
                status=IngestionStatus.FAILED_NOT_FOUND,
                filename=source_path.name,
                source_path=str(source_path),
                message=f"File not found: {source_path}"
            )

        # 1. Compute SHA-256 hash
        try:
            file_hash = compute_file_sha256(source_path)
        except Exception as e:
            logger.error("Failed to compute SHA-256 for %s: %s", source_path, e)
            return IngestionResult(
                status=IngestionStatus.FAILED_CORRUPTED,
                filename=source_path.name,
                source_path=str(source_path),
                message=f"Could not read file for hashing: {e}"
            )

        # 2. Inspect PDF validity using PyMuPDF
        try:
            pdf_doc = pymupdf.open(source_path)
        except Exception as e:
            logger.warning("Corrupted or unsupported PDF '%s': %s", source_path.name, e)
            return IngestionResult(
                status=IngestionStatus.FAILED_CORRUPTED,
                filename=source_path.name,
                source_path=str(source_path),
                file_hash=file_hash,
                message=f"Corrupted or invalid PDF file: {e}"
            )

        try:
            if pdf_doc.is_encrypted:
                pdf_doc.close()
                logger.warning("PDF '%s' is password encrypted", source_path.name)
                return IngestionResult(
                    status=IngestionStatus.FAILED_ENCRYPTED,
                    filename=source_path.name,
                    source_path=str(source_path),
                    file_hash=file_hash,
                    message="PDF is password encrypted. Unencrypted files required."
                )

            page_count = len(pdf_doc)
            if page_count < 1:
                pdf_doc.close()
                return IngestionResult(
                    status=IngestionStatus.FAILED_CORRUPTED,
                    filename=source_path.name,
                    source_path=str(source_path),
                    file_hash=file_hash,
                    message="PDF contains no pages."
                )

            # 3. Check for existing document by filename in this project
            existing_doc = self.repo.get_document_by_filename(project_id, source_path.name)

            if existing_doc is not None:
                # Check latest revision hash
                latest_rev = self.repo.get_latest_revision(existing_doc.id)
                if latest_rev and latest_rev.file_hash == file_hash:
                    pdf_doc.close()
                    logger.info("Unchanged duplicate file '%s' detected (hash: %s)", source_path.name, file_hash[:12])
                    return IngestionResult(
                        status=IngestionStatus.DUPLICATE_IGNORED,
                        filename=source_path.name,
                        source_path=str(source_path),
                        document_id=existing_doc.id,
                        revision_id=latest_rev.id,
                        revision_code=latest_rev.revision_code,
                        file_hash=file_hash,
                        page_count=page_count,
                        message=f"Unchanged duplicate of {latest_rev.revision_code} ignored."
                    )

                # Different hash! Create new revision
                all_revisions = self.repo.list_revisions(existing_doc.id)
                rev_idx = len(all_revisions) + 1
                rev_code = f"rev{rev_idx:02d}"
                document_id = existing_doc.id
                status = IngestionStatus.SUCCESS_NEW_REVISION
            else:
                # New document
                document = Document(
                    project_id=project_id,
                    filename=source_path.name,
                    doc_type=doc_type,
                    is_immutable=True
                )
                self.repo.save_document(document)
                document_id = document.id
                rev_code = "rev01"
                status = IngestionStatus.SUCCESS_NEW_DOCUMENT

            # 4. Copy to immutable storage
            doc_storage_dir = self.storage_dir / str(document_id)
            doc_storage_dir.mkdir(parents=True, exist_ok=True)
            stored_file_path = doc_storage_dir / f"{rev_code}_{source_path.name}"

            shutil.copy2(source_path, stored_file_path)

            # Verify integrity of copied file
            if not verify_file_sha256(stored_file_path, file_hash):
                stored_file_path.unlink(missing_ok=True)
                pdf_doc.close()
                raise DocumentImmutabilityError(
                    f"Integrity check failed copying {source_path.name} to project store."
                )

            # 5. Create DocumentRevision
            # Store relative path from project root
            rel_storage_path = str(stored_file_path.relative_to(self.project_dir))
            revision = DocumentRevision(
                document_id=document_id,
                revision_code=rev_code,
                file_hash=file_hash,
                source_path=rel_storage_path,
                is_current=True,
                metadata={"original_source_path": str(source_path.resolve())}
            )
            self.repo.save_revision(revision)

            # 6. Extract page geometries and register Page records
            for p_idx in range(page_count):
                pdf_page = pdf_doc[p_idx]
                rect = pdf_page.rect
                rotation = pdf_page.rotation

                geometry = PageGeometry(
                    width_pt=rect.width,
                    height_pt=rect.height,
                    rotation=rotation,
                    origin=CoordinateOrigin.TOP_LEFT,
                    dpi=72.0,
                    scale=DrawingScale(status=ScaleStatus.UNSCALED)
                )

                page_model = Page(
                    revision_id=revision.id,
                    page_number=p_idx + 1,
                    geometry=geometry,
                    metadata={"crop_box": [rect.x0, rect.y0, rect.x1, rect.y1]}
                )
                self.repo.save_page(page_model)

            pdf_doc.close()
            logger.info("Successfully ingested '%s' as %s (%d pages)", source_path.name, rev_code, page_count)

            return IngestionResult(
                status=status,
                filename=source_path.name,
                source_path=str(source_path),
                document_id=document_id,
                revision_id=revision.id,
                revision_code=rev_code,
                file_hash=file_hash,
                page_count=page_count,
                message=f"Successfully ingested as {rev_code} with {page_count} pages."
            )

        except Exception as e:
            pdf_doc.close()
            logger.error("Failed ingesting %s: %s", source_path.name, e)
            raise

    def ingest_directory(
        self,
        project_id: UUID,
        dir_path: Path,
        doc_type: DocumentType = DocumentType.ARCHITECTURAL_PLAN,
        recursive: bool = False
    ) -> list[IngestionResult]:
        """Ingest all PDF files found in a directory."""
        directory = Path(dir_path)
        if not directory.is_dir():
            raise FileNotFoundError(f"Directory not found: {directory}")

        pattern = "**/*.pdf" if recursive else "*.pdf"
        results = []
        for pdf_file in sorted(directory.glob(pattern)):
            if pdf_file.is_file():
                res = self.ingest_file(project_id, pdf_file, doc_type=doc_type)
                results.append(res)
        return results
