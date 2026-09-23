"""Vector and text extraction from CAD PDF drawings preserving canonical coordinates."""

from enum import StrEnum
from typing import Any, Optional
import pymupdf
from pydantic import BaseModel, Field

from tz_plan_pipeline.extraction.inventory import PageInventory, inspect_page_inventory
from tz_plan_pipeline.models.common import BoundingBox, Point2D


class ExtractedTextSpan(BaseModel):
    """Raw text span extracted from PDF text layer with exact coordinates."""
    text: str = Field(description="Extracted text string")
    bbox: BoundingBox = Field(description="Canonical PDF bounding box coordinates in points (pt)")
    font_name: Optional[str] = Field(default=None, description="Font identifier")
    font_size: float = Field(description="Font size in points")
    flags: int = Field(default=0, description="PyMuPDF font flags (bold, italic, etc.)")
    color: int = Field(default=0, description="Text color integer (sRGB)")


class VectorCommandType(StrEnum):
    """Geometry command in a vector drawing path."""
    LINE = "line"
    RECT = "rect"
    CURVE = "curve"


class VectorCommand(BaseModel):
    """Individual geometric segment within a vector path."""
    command_type: VectorCommandType
    points: list[Point2D] = Field(description="Vertices defining the line, rect, or bezier curve")


class ExtractedVectorPath(BaseModel):
    """Raw vector drawing path extracted from CAD drawing streams."""
    bbox: BoundingBox = Field(description="Enclosing bounding box of the vector path")
    items: list[VectorCommand] = Field(default_factory=list, description="List of geometric drawing commands")
    stroke_color: Optional[tuple[float, ...]] = Field(default=None, description="Stroke color components (RGB/CMYK)")
    fill_color: Optional[tuple[float, ...]] = Field(default=None, description="Fill color components (RGB/CMYK)")
    width: float = Field(default=1.0, description="Stroke line width in points")


class ExtractedImage(BaseModel):
    """Metadata and canonical bounding box of an embedded raster image."""
    xref: int = Field(description="PyMuPDF image object xref ID")
    bbox: BoundingBox = Field(description="Placement bounding box on page in points (pt)")
    pixel_width: int = Field(gt=0, description="Image bitmap width in pixels")
    pixel_height: int = Field(gt=0, description="Image bitmap height in pixels")
    colorspace: str = Field(description="Colorspace name (DeviceRGB, DeviceGray, etc.)")


class PageExtractionResult(BaseModel):
    """Structured extraction output for a single drawing page."""
    page_number: int
    inventory: PageInventory
    text_spans: list[ExtractedTextSpan] = Field(default_factory=list)
    vector_paths: list[ExtractedVectorPath] = Field(default_factory=list)
    images: list[ExtractedImage] = Field(default_factory=list)


def safe_bbox(rect: Any) -> BoundingBox:
    """Construct a BoundingBox ensuring x0 <= x1 and y0 <= y1."""
    x0, y0, x1, y1 = float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3])
    return BoundingBox(
        x0=min(x0, x1),
        y0=min(y0, y1),
        x1=max(x0, x1),
        y1=max(y0, y1)
    )


def extract_page_content(page: pymupdf.Page) -> PageExtractionResult:
    """Extract raw text spans, vector geometry paths, and embedded images from a page.

    Preserves exact canonical PDF coordinates (pt) without interpreting architectural semantics.
    """
    inventory = inspect_page_inventory(page)

    # 1. Text extraction
    extracted_spans: list[ExtractedTextSpan] = []
    text_dict = page.get_text("dict", flags=pymupdf.TEXT_DEHYPHENATE)
    for block in text_dict.get("blocks", []):
        if block.get("type") == 0:  # Text block
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    span_text = span.get("text", "").strip()
                    if span_text:
                        extracted_spans.append(ExtractedTextSpan(
                            text=span_text,
                            bbox=safe_bbox(span.get("bbox", (0, 0, 0, 0))),
                            font_name=span.get("font"),
                            font_size=span.get("size", 10.0),
                            flags=span.get("flags", 0),
                            color=span.get("color", 0)
                        ))

    # 2. Vector path extraction
    extracted_vectors: list[ExtractedVectorPath] = []
    drawings = page.get_drawings()
    for draw in drawings:
        rect = draw.get("rect", (0, 0, 0, 0))
        commands: list[VectorCommand] = []

        for item in draw.get("items", []):
            item_type = item[0]
            if item_type == "l":  # Line: ('l', p1, p2)
                p1, p2 = item[1], item[2]
                commands.append(VectorCommand(
                    command_type=VectorCommandType.LINE,
                    points=[Point2D(x=p1.x, y=p1.y), Point2D(x=p2.x, y=p2.y)]
                ))
            elif item_type == "re":  # Rect: ('re', rect)
                r = item[1]
                commands.append(VectorCommand(
                    command_type=VectorCommandType.RECT,
                    points=[
                        Point2D(x=r.x0, y=r.y0),
                        Point2D(x=r.x1, y=r.y0),
                        Point2D(x=r.x1, y=r.y1),
                        Point2D(x=r.x0, y=r.y1)
                    ]
                ))
            elif item_type == "c":  # Bezier curve: ('c', p1, p2, p3, p4)
                p1, p2, p3, p4 = item[1], item[2], item[3], item[4]
                commands.append(VectorCommand(
                    command_type=VectorCommandType.CURVE,
                    points=[
                        Point2D(x=p1.x, y=p1.y),
                        Point2D(x=p2.x, y=p2.y),
                        Point2D(x=p3.x, y=p3.y),
                        Point2D(x=p4.x, y=p4.y)
                    ]
                ))

        extracted_vectors.append(ExtractedVectorPath(
            bbox=safe_bbox(rect),
            items=commands,
            stroke_color=draw.get("color"),
            fill_color=draw.get("fill"),
            width=draw.get("width", 1.0)
        ))

    # 3. Image extraction
    extracted_images: list[ExtractedImage] = []
    image_list = page.get_images()
    for img_info in image_list:
        xref = img_info[0]
        # Find where this image is placed on page
        rects = page.get_image_rects(xref)
        bbox = safe_bbox(rects[0]) if rects else BoundingBox(x0=0, y0=0, x1=page.rect.width, y1=page.rect.height)
        extracted_images.append(ExtractedImage(
            xref=xref,
            bbox=bbox,
            pixel_width=img_info[2],
            pixel_height=img_info[3],
            colorspace=str(img_info[5])
        ))

    return PageExtractionResult(
        page_number=page.number + 1,
        inventory=inventory,
        text_spans=extracted_spans,
        vector_paths=extracted_vectors,
        images=extracted_images
    )
