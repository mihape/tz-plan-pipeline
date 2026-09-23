"""Diagnostic extraction reporting and visual overlay generation."""

import json
from pathlib import Path
from typing import Any, Optional
from uuid import UUID
import pymupdf
from pydantic import BaseModel, Field

from tz_plan_pipeline.extraction.dimensions import DimensionCandidate
from tz_plan_pipeline.extraction.pdf_extractor import PageExtractionResult
from tz_plan_pipeline.extraction.scale import ScaleCandidate


class PageReportSummary(BaseModel):
    """Summary of extraction findings on an individual page."""
    page_number: int
    content_class: str
    width_pt: float
    height_pt: float
    rotation: int
    text_spans: int
    vector_paths: int
    images: int
    dimension_candidates: int
    scale_candidates: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExtractionReport(BaseModel):
    """Diagnostic report summarizing PDF extraction findings and quality metrics."""
    document_id: UUID
    revision_id: UUID
    filename: str
    file_hash: str
    page_count: int
    pages: list[PageReportSummary] = Field(default_factory=list)
    total_text_spans: int = 0
    total_vector_paths: int = 0
    total_images: int = 0
    total_dimension_candidates: int = 0
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def to_markdown(self) -> str:
        """Format the extraction report as clean GitHub-style Markdown."""
        lines = [
            f"# Extraction Report: {self.filename}",
            "",
            f"- **Document ID:** `{self.document_id}`",
            f"- **Revision ID:** `{self.revision_id}`",
            f"- **SHA-256:** `{self.file_hash}`",
            f"- **Page Count:** {self.page_count}",
            f"- **Total Text Spans:** {self.total_text_spans}",
            f"- **Total Vector Paths:** {self.total_vector_paths}",
            f"- **Total Images:** {self.total_images}",
            f"- **Total Dimension Candidates:** {self.total_dimension_candidates}",
            "",
            "## Page Breakdown",
            "",
            "| Page | Class | Dimensions (pt) | Rotation | Text | Vectors | Images | Dims | Scale Candidates |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for p in self.pages:
            scales_str = ", ".join(p.scale_candidates) or "None"
            lines.append(
                f"| {p.page_number} | `{p.content_class}` | {p.width_pt:.1f}x{p.height_pt:.1f} | {p.rotation}° | "
                f"{p.text_spans} | {p.vector_paths} | {p.images} | {p.dimension_candidates} | {scales_str} |"
            )

        if self.warnings:
            lines.extend(["", "## Warnings", ""])
            for w in self.warnings:
                lines.append(f"- ⚠️ {w}")

        if self.errors:
            lines.extend(["", "## Errors", ""])
            for e in self.errors:
                lines.append(f"- ❌ {e}")

        return "\n".join(lines)

    def save_markdown(self, path: Path) -> None:
        """Save report as markdown."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_markdown())

    def save_json(self, path: Path) -> None:
        """Save report as JSON."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.model_dump_json(indent=2))


class DiagnosticOverlayRenderer:
    """Renders visual diagnostic overlays with bounding boxes over drawing pages.

    NEVER modifies the original PDF file.
    """

    @staticmethod
    def render_overlay(
        source_pdf_path: Path,
        page_number: int,
        output_path: Path,
        extraction_result: PageExtractionResult,
        dimension_candidates: list[DimensionCandidate],
        scale_candidates: list[ScaleCandidate],
        format: str = "png",
        dpi: float = 150.0
    ) -> Path:
        """Render diagnostic overlays highlighting text spans, dimensions, and scales.

        Args:
            source_pdf_path: Path to the untouched original PDF.
            page_number: 1-indexed page number to render.
            output_path: Target path for the generated diagnostic file.
            extraction_result: Extracted raw page content.
            dimension_candidates: Detected dimension candidates.
            scale_candidates: Detected scale label candidates.
            format: 'png' or 'pdf'.
            dpi: Rendering DPI for raster PNG output.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        doc = pymupdf.open(source_pdf_path)
        try:
            page = doc[page_number - 1]
            shape = page.new_shape()

            # 1. Text spans: thin blue outlines
            for span in extraction_result.text_spans:
                rect = pymupdf.Rect(span.bbox.x0, span.bbox.y0, span.bbox.x1, span.bbox.y1)
                shape.draw_rect(rect)
                shape.finish(color=(0.1, 0.4, 0.9), width=0.5)

            # 2. Dimension candidates: green rectangles with highlight
            for dim in dimension_candidates:
                rect = pymupdf.Rect(dim.bbox.x0, dim.bbox.y0, dim.bbox.x1, dim.bbox.y1)
                shape.draw_rect(rect)
                shape.finish(color=(0.1, 0.8, 0.2), fill=(0.8, 1.0, 0.8), fill_opacity=0.3, width=1.0)

            # 3. Scale candidates: orange rectangles with highlight
            for scale in scale_candidates:
                rect = pymupdf.Rect(scale.bbox.x0, scale.bbox.y0, scale.bbox.x1, scale.bbox.y1)
                shape.draw_rect(rect)
                shape.finish(color=(0.9, 0.5, 0.1), fill=(1.0, 0.9, 0.7), fill_opacity=0.4, width=1.5)

            shape.commit()

            if format.lower() == "png":
                pix = page.get_pixmap(dpi=int(dpi))
                pix.save(output_path)
            elif format.lower() == "pdf":
                # Create a single-page diagnostic PDF
                diag_doc = pymupdf.open()
                diag_doc.insert_pdf(doc, from_page=page_number - 1, to_page=page_number - 1)
                diag_doc.save(output_path)
                diag_doc.close()
            else:
                raise ValueError(f"Unsupported diagnostic format '{format}'. Use 'png' or 'pdf'.")

            return output_path
        finally:
            doc.close()
