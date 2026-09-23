"""Programmatic synthetic PDF generators for automated testing."""

import io
from pathlib import Path
from PIL import Image as PILImage
import pymupdf


def create_synthetic_image_bytes(width: int = 200, height: int = 150, color=(180, 200, 220)) -> bytes:
    """Generate in-memory PNG image bytes using Pillow."""
    img = PILImage.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_synthetic_vector_plan_pdf(
    output_path: Path,
    pages: int = 2,
    rotation: int = 0,
    include_scale_label: str = "M 1:50"
) -> Path:
    """Create a synthetic vector-based architectural drawing PDF.

    Includes walls, dimension lines, tick marks, and Hungarian dimension annotations.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    doc = pymupdf.open()
    for p_idx in range(pages):
        page = doc.new_page(width=841.89, height=595.28)  # A4 Landscape (pt)
        if rotation != 0:
            page.set_rotation(rotation)

        shape = page.new_shape()

        # 1. Outer perimeter wall rect (Vector)
        shape.draw_rect(pymupdf.Rect(100, 100, 700, 500))
        shape.finish(color=(0, 0, 0), fill=(0.95, 0.95, 0.95), width=2.0)

        # 2. Interior partition line
        shape.draw_line(pymupdf.Point(350, 100), pymupdf.Point(350, 500))
        shape.finish(color=(0, 0, 0), width=1.5)

        # 3. Known dimension line for scale calibration test
        # Stated distance = 5.00 m at 1:50 scale.
        # Paper meters = 5.0 / 50 = 0.10 m.
        # Length in pt = 0.10 / (0.0254 / 72) = 283.464567 pt.
        x_start = 100.0
        x_end = 100.0 + 283.464567
        y_dim = 70.0
        shape.draw_line(pymupdf.Point(x_start, y_dim), pymupdf.Point(x_end, y_dim))
        # Tick marks
        shape.draw_line(pymupdf.Point(x_start, y_dim - 5), pymupdf.Point(x_start, y_dim + 5))
        shape.draw_line(pymupdf.Point(x_end, y_dim - 5), pymupdf.Point(x_end, y_dim + 5))
        shape.finish(color=(0.2, 0.2, 0.2), width=0.75)
        shape.commit()

        # Text labels (Hungarian architectural annotations)
        # Title block
        page.insert_text(pymupdf.Point(550, 530), f"ALAPRAJZ - {p_idx + 1}. LAP", fontsize=14)
        if include_scale_label:
            page.insert_text(pymupdf.Point(550, 550), f"Méretarány: {include_scale_label}", fontsize=11)

        # Dimension line text
        mid_x = (x_start + x_end) / 2.0 - 15
        page.insert_text(pymupdf.Point(mid_x, y_dim - 3), "5,00", fontsize=9)

        # Opening schedule callout: "150/150", "pm. 90"
        page.insert_text(pymupdf.Point(220, 95), "150/150", fontsize=9)
        page.insert_text(pymupdf.Point(220, 85), "pm. 90", fontsize=8)

        # Another opening callout
        page.insert_text(pymupdf.Point(340, 300), "90/210", fontsize=9)

        # Level mark: "+0,00"
        page.insert_text(pymupdf.Point(200, 200), "+0,00", fontsize=10)

        # Linear dimension in cm: "240"
        page.insert_text(pymupdf.Point(500, 300), "240", fontsize=9)

    doc.save(path)
    doc.close()
    return path


def create_synthetic_raster_pdf(output_path: Path) -> Path:
    """Create a PDF consisting purely of a scanned/raster image without vector or text."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    img_bytes = create_synthetic_image_bytes(width=600, height=800, color=(240, 240, 240))
    page.insert_image(pymupdf.Rect(0, 0, 600, 800), stream=img_bytes)

    doc.save(path)
    doc.close()
    return path


def create_synthetic_mixed_pdf(output_path: Path) -> Path:
    """Create a PDF containing both vector geometry/text and an embedded raster image."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    doc = pymupdf.open()
    page = doc.new_page(width=841.89, height=595.28)

    # Vector box
    shape = page.new_shape()
    shape.draw_rect(pymupdf.Rect(50, 50, 400, 400))
    shape.finish(color=(0, 0, 0), width=1.0)
    shape.commit()

    page.insert_text(pymupdf.Point(60, 80), "Helyszínrajz M 1:500", fontsize=12)

    # Embedded site photo / raster orthophoto
    img_bytes = create_synthetic_image_bytes(width=300, height=300, color=(100, 150, 100))
    page.insert_image(pymupdf.Rect(450, 50, 750, 350), stream=img_bytes)

    doc.save(path)
    doc.close()
    return path


def create_encrypted_pdf(output_path: Path, password: str = "secret") -> Path:
    """Create a password-encrypted PDF."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    doc = pymupdf.open()
    page = doc.new_page(width=500, height=500)
    page.insert_text(pymupdf.Point(50, 50), "Confidential Architectural Data", fontsize=12)

    perm = int(
        pymupdf.PDF_PERM_PRINT
        | pymupdf.PDF_PERM_COPY
        | pymupdf.PDF_PERM_ANNOTATE
    )
    doc.save(
        path,
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        user_pw=password,
        owner_pw=password,
        permissions=perm
    )
    doc.close()
    return path


def create_corrupted_pdf(output_path: Path) -> Path:
    """Create an invalid/corrupted PDF file containing random non-PDF bytes."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"%PDF-1.4\nCorrupted content completely invalid \x00\xff\xfe\xca\xfe\xba\xbe")
    return path
