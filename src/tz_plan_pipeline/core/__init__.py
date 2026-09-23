"""Core infrastructure, coordinate systems, units, and errors for TZ Plan Pipeline."""

from tz_plan_pipeline.core.errors import (
    ApprovalSimulationError,
    ConflictingEvidenceError,
    ConfigurationError,
    DocumentImmutabilityError,
    MissingDataError,
    ProvenanceError,
    ScaleCalibrationError,
    StorageError,
    TZPipelineError,
    UncalibratedScaleError,
    UnitConversionError,
)
from tz_plan_pipeline.core.units import (
    UnitDimension,
    convert_from_si,
    convert_to_si,
    convert_units,
    get_unit_dimension,
)
from tz_plan_pipeline.core.coordinates import (
    CoordinateOrigin,
    DrawingScale,
    PageGeometry,
    ScaleStatus,
    pixels_to_pt,
    pt_to_pixels,
    pt_to_real_world_meters,
    real_world_meters_to_pt,
)

__all__ = [
    "ApprovalSimulationError",
    "ConflictingEvidenceError",
    "ConfigurationError",
    "CoordinateOrigin",
    "DocumentImmutabilityError",
    "DrawingScale",
    "MissingDataError",
    "PageGeometry",
    "ProvenanceError",
    "ScaleCalibrationError",
    "ScaleStatus",
    "StorageError",
    "TZPipelineError",
    "UncalibratedScaleError",
    "UnitConversionError",
    "UnitDimension",
    "convert_from_si",
    "convert_to_si",
    "convert_units",
    "get_unit_dimension",
    "pixels_to_pt",
    "pt_to_pixels",
    "pt_to_real_world_meters",
    "real_world_meters_to_pt",
]
