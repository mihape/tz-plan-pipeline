"""PDF Page inventory, object counting, and vector/raster classification heuristics."""

from enum import StrEnum
import re
from typing import Optional
import pymupdf
from pydantic import BaseModel, Field

# Common Hungarian / architectural drawing scale regex
SCALE_PATTERN = re.compile(
    r"(?:m(?:éretarány)?\s*[:=]?\s*1\s*[:/]\s*(\d+)|1\s*[:/]\s*(\d{2,4}))",
    re.IGNORECASE
)


class PageContentClass(StrEnum):
    """Classification of drawing content representation on a page."""
    VECTOR_ONLY = "vector_only"  # Native CAD vector geometry & selectable text
    RASTER_ONLY = "raster_only"  # Scanned image / bitmap only, no vector or text
    MIXED = "mixed"              # Combination of vector geometry/text and raster images
    EMPTY = "empty"              # Blank page or background only


class PageInventory(BaseModel):
    """Inventory of geometric and textual objects on a single PDF page."""
    page_number: int = Field(ge=1, description="1-indexed physical page number")
    width_pt: float = Field(gt=0, description="Page width in canonical PDF points")
    height_pt: float = Field(gt=0, description="Page height in canonical PDF points")
    rotation: int = Field(description="Page rotation (0, 90, 180, 270)")
    text_span_count: int = Field(ge=0, description="Total text spans detected")
    vector_path_count: int = Field(ge=0, description="Total vector drawing paths detected")
    image_count: int = Field(ge=0, description="Total embedded raster images detected")
    content_class: PageContentClass = Field(description="Heuristic classification")
    classification_reason: str = Field(description="Explanation of classification")
    fonts_detected: list[str] = Field(default_factory=list, description="Unique font family names detected")
    scale_label_candidates: list[str] = Field(
        default_factory=list,
        description="Candidate scale text labels found on the sheet"
    )


def classify_page_content(
    text_span_count: int,
    vector_path_count: int,
    image_count: int
) -> tuple[PageContentClass, str]:
    """Classify page content using documented, deterministic heuristics.

    Heuristic Rules:
    1. EMPTY: 0 text spans, 0 vector paths, 0 images.
    2. RASTER_ONLY: >= 1 image, 0 vector paths, and fewer than 5 text spans (e.g. scanned drawings).
    3. VECTOR_ONLY: 0 images, and (>= 1 vector path or >= 5 text spans). Typical CAD export.
    4. MIXED: >= 1 image AND (>= 1 vector path or >= 5 text spans). E.g. vector plan with orthophoto / company logo.
    """
    if image_count == 0 and vector_path_count == 0 and text_span_count == 0:
        return PageContentClass.EMPTY, "Page contains no text, vector paths, or images."

    if image_count > 0 and vector_path_count == 0 and text_span_count < 5:
        return (
            PageContentClass.RASTER_ONLY,
            f"Page contains {image_count} raster image(s) with no vector geometry and negligible text ({text_span_count} spans)."
        )

    if image_count == 0 and (vector_path_count > 0 or text_span_count >= 5):
        return (
            PageContentClass.VECTOR_ONLY,
            f"Page contains native vector drawings ({vector_path_count} paths) and text ({text_span_count} spans) with no raster images."
        )

    if image_count > 0 and (vector_path_count > 0 or text_span_count >= 5):
        return (
            PageContentClass.MIXED,
            f"Page contains both raster images ({image_count}) and vector/text elements ({vector_path_count} paths, {text_span_count} spans)."
        )

    # Edge cases (e.g. 1-4 text spans, 0 vectors, 0 images)
    return PageContentClass.VECTOR_ONLY, f"Sparse text page ({text_span_count} spans)."


def inspect_page_inventory(page: pymupdf.Page) -> PageInventory:
    """Analyze a single PyMuPDF page and return its structured inventory."""
    rect = page.rect
    rotation = page.rotation

    # 1. Text spans and fonts
    text_dict = page.get_text("dict", flags=pymupdf.TEXT_DEHYPHENATE)
    text_spans: list[str] = []
    fonts: set[str] = set()
    scale_labels: list[str] = []

    for block in text_dict.get("blocks", []):
        if block.get("type") == 0:  # Text block
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    span_text = span.get("text", "").strip()
                    if span_text:
                        text_spans.append(span_text)
                        font = span.get("font")
                        if font:
                            fonts.add(font)

                        # Check for scale candidates
                        if SCALE_PATTERN.search(span_text):
                            scale_labels.append(span_text)

    # 2. Vector drawings
    drawings = page.get_drawings()
    vector_path_count = len(drawings)

    # 3. Images
    images = page.get_images()
    image_count = len(images)

    # 4. Classification
    content_class, reason = classify_page_content(
        text_span_count=len(text_spans),
        vector_path_count=vector_path_count,
        image_count=image_count
    )

    return PageInventory(
        page_number=page.number + 1,
        width_pt=rect.width,
        height_pt=rect.height,
        rotation=rotation,
        text_span_count=len(text_spans),
        vector_path_count=vector_path_count,
        image_count=image_count,
        content_class=content_class,
        classification_reason=reason,
        fonts_detected=sorted(list(fonts)),
        scale_label_candidates=scale_labels
    )
