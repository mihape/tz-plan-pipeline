"""Canonical PDF coordinate system, scale semantics, and geometric transformations.

Canonical PDF Coordinate Conventions:
- 1 PDF point = 1/72 inch = 0.352778 mm = 0.000352778 m.
- Standard PDF page coordinates (pt): origin (0, 0) is canonical.
- Rendered image pixel coordinates depend on target DPI (pixels = pt * dpi / 72.0).
- Scale semantics strictly separate 'declared' scale (e.g. printed text '1:50') from
  'calibrated' scale (empirically verified against known dimension lines).
- Uncalibrated or failed scales are prohibited from producing authoritative real-world measurements.
"""

from enum import StrEnum
from typing import Optional
from pydantic import BaseModel, Field, model_validator

from tz_plan_pipeline.core.errors import UncalibratedScaleError, ScaleCalibrationError
from tz_plan_pipeline.core.units import PT_TO_M_FACTOR


class ScaleStatus(StrEnum):
    """Lifecycle and calibration status of a drawing scale."""
    UNSCALED = "unscaled"               # No scale information available
    DECLARED = "declared"               # Printed/noted on sheet (e.g. 'M=1:50'), NOT authoritative
    CALIBRATED = "calibrated"           # Empirically verified against dimension evidence
    FAILED_CALIBRATION = "failed_calibration"  # Calibration failed tolerance checks


class CoordinateOrigin(StrEnum):
    """Origin reference for coordinates."""
    TOP_LEFT = "top_left"       # Standard viewer / PyMuPDF default
    BOTTOM_LEFT = "bottom_left" # Standard PostScript / native PDF default


class DrawingScale(BaseModel):
    """Represents drawing scale with strict separation between declared label and calibrated ratio.

    A printed label like '1:50' is a declared hypothesis. It is NOT authoritative until calibrated.
    """
    status: ScaleStatus = ScaleStatus.UNSCALED
    declared_ratio: Optional[float] = Field(
        default=None,
        description="Declared denominator, e.g. 50.0 for 1:50 scale"
    )
    declared_label: Optional[str] = Field(
        default=None,
        description="Literal text found on drawing title block, e.g. 'M = 1:50'"
    )
    calibrated_ratio: Optional[float] = Field(
        default=None,
        description="Measured denominator after calibration, e.g. 50.15"
    )
    calibrated_by: Optional[str] = Field(
        default=None,
        description="Identifier of calibrating entity or rule"
    )
    calibration_evidence_id: Optional[str] = Field(
        default=None,
        description="UUID of dimension line evidence used for calibration"
    )
    tolerance_percent: float = Field(
        default=1.0,
        description="Allowed tolerance percentage between declared and calibrated ratios"
    )

    @model_validator(mode="after")
    def validate_scale_consistency(self) -> "DrawingScale":
        if self.status == ScaleStatus.CALIBRATED:
            if self.calibrated_ratio is None or self.calibrated_ratio <= 0:
                raise ValueError("Calibrated scale must have a positive calibrated_ratio")
        return self

    def is_authoritative(self) -> bool:
        """Only calibrated scale is authoritative for real-world engineering measurements."""
        return self.status == ScaleStatus.CALIBRATED and self.calibrated_ratio is not None

    def get_effective_ratio(self, require_authoritative: bool = True) -> float:
        """Return the effective scale ratio denominator.

        Args:
            require_authoritative: If True, raises UncalibratedScaleError if scale is not CALIBRATED.
        """
        if require_authoritative:
            if not self.is_authoritative():
                raise UncalibratedScaleError(
                    f"Cannot produce authoritative real-world measurements with scale status '{self.status}'. "
                    "Printed scale labels ('declared') must be calibrated before use."
                )
            assert self.calibrated_ratio is not None
            return self.calibrated_ratio

        # Non-authoritative / exploratory mode
        if self.calibrated_ratio is not None:
            return self.calibrated_ratio
        if self.declared_ratio is not None and self.declared_ratio > 0:
            return self.declared_ratio
        raise UncalibratedScaleError("No scale ratio (neither calibrated nor declared) is available.")

    def calibrate(
        self,
        measured_pt: float,
        actual_meters: float,
        evidence_id: Optional[str] = None,
        calibrated_by: Optional[str] = None
    ) -> "DrawingScale":
        """Calibrate this scale against a verified physical dimension line.

        Args:
            measured_pt: Measured distance in PDF points.
            actual_meters: Stated real-world distance in SI meters.
            evidence_id: Optional evidence identifier of the dimension line.
            calibrated_by: Optional operator or algorithm name.
        """
        if measured_pt <= 0 or actual_meters <= 0:
            raise ScaleCalibrationError("Calibration distances must be strictly positive")

        # In meters on paper: paper_meters = measured_pt * PT_TO_M_FACTOR
        paper_meters = measured_pt * PT_TO_M_FACTOR
        calculated_ratio = actual_meters / paper_meters

        if self.declared_ratio is not None and self.declared_ratio > 0:
            diff_pct = abs(calculated_ratio - self.declared_ratio) / self.declared_ratio * 100.0
            if diff_pct > self.tolerance_percent:
                return DrawingScale(
                    status=ScaleStatus.FAILED_CALIBRATION,
                    declared_ratio=self.declared_ratio,
                    declared_label=self.declared_label,
                    calibrated_ratio=calculated_ratio,
                    calibration_evidence_id=evidence_id,
                    calibrated_by=calibrated_by,
                    tolerance_percent=self.tolerance_percent
                )

        return DrawingScale(
            status=ScaleStatus.CALIBRATED,
            declared_ratio=self.declared_ratio,
            declared_label=self.declared_label,
            calibrated_ratio=calculated_ratio,
            calibration_evidence_id=evidence_id,
            calibrated_by=calibrated_by,
            tolerance_percent=self.tolerance_percent
        )


class PageGeometry(BaseModel):
    """Geometric properties and coordinate system definition for a single document page."""
    width_pt: float = Field(gt=0, description="Canonical page width in PDF points (1/72 in)")
    height_pt: float = Field(gt=0, description="Canonical page height in PDF points (1/72 in)")
    rotation: int = Field(default=0, description="Page rotation in degrees (0, 90, 180, 270)")
    origin: CoordinateOrigin = Field(default=CoordinateOrigin.TOP_LEFT)
    dpi: float = Field(default=72.0, gt=0, description="Native reference DPI (72 for standard PDF points)")
    scale: DrawingScale = Field(default_factory=DrawingScale)

    @model_validator(mode="after")
    def validate_rotation(self) -> "PageGeometry":
        if self.rotation not in (0, 90, 180, 270):
            raise ValueError(f"Invalid page rotation '{self.rotation}'. Must be 0, 90, 180, or 270.")
        return self


# Coordinate and Conversion Functions

def pt_to_pixels(pt: float, dpi: float = 300.0) -> float:
    """Convert canonical PDF points to raster image pixels at a target rendering DPI."""
    if dpi <= 0:
        raise ValueError("DPI must be strictly positive")
    return pt * (dpi / 72.0)


def pixels_to_pt(pixels: float, dpi: float = 300.0) -> float:
    """Convert raster image pixels at given DPI back to canonical PDF points."""
    if dpi <= 0:
        raise ValueError("DPI must be strictly positive")
    return pixels * (72.0 / dpi)


def pt_to_real_world_meters(
    pt: float,
    scale: DrawingScale,
    require_authoritative: bool = True
) -> float:
    """Convert distance in PDF points to real-world engineering meters.

    Raises:
        UncalibratedScaleError: If require_authoritative is True and scale is not CALIBRATED.
    """
    ratio = scale.get_effective_ratio(require_authoritative=require_authoritative)
    # 1 pt = PT_TO_M_FACTOR meters on paper.
    # Real world meters = paper meters * scale_ratio
    return pt * PT_TO_M_FACTOR * ratio


def real_world_meters_to_pt(
    meters: float,
    scale: DrawingScale,
    require_authoritative: bool = True
) -> float:
    """Convert real-world engineering meters to drawing distance in PDF points."""
    ratio = scale.get_effective_ratio(require_authoritative=require_authoritative)
    if ratio <= 0:
        raise ValueError("Scale ratio must be positive")
    return meters / (PT_TO_M_FACTOR * ratio)
