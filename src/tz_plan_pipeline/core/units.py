"""Internal SI unit conversion and validation engine for TZ Plan Pipeline.

Enforces consistent internal SI units (meters, square meters, cubic meters, kilograms)
with explicit bidirectional conversions.
"""

from enum import StrEnum
from typing import Final

from tz_plan_pipeline.core.errors import UnitConversionError


class UnitDimension(StrEnum):
    """Physical dimensions for construction measurements."""
    LENGTH = "length"
    AREA = "area"
    VOLUME = "volume"
    MASS = "mass"
    COUNT = "count"


# Canonical internal SI base units
SI_BASE_UNITS: Final[dict[UnitDimension, str]] = {
    UnitDimension.LENGTH: "m",
    UnitDimension.AREA: "m2",
    UnitDimension.VOLUME: "m3",
    UnitDimension.MASS: "kg",
    UnitDimension.COUNT: "piece",
}

# Conversion multipliers: value_in_unit * FACTOR = value_in_SI_base
# 1 inch = 0.0254 m; 1 pt = 1/72 inch = 0.0254 / 72 m
PT_TO_M_FACTOR: Final[float] = 0.0254 / 72.0

UNIT_FACTORS: Final[dict[str, tuple[UnitDimension, float]]] = {
    # Length -> meters (m)
    "m": (UnitDimension.LENGTH, 1.0),
    "meter": (UnitDimension.LENGTH, 1.0),
    "meters": (UnitDimension.LENGTH, 1.0),
    "cm": (UnitDimension.LENGTH, 0.01),
    "centimeter": (UnitDimension.LENGTH, 0.01),
    "mm": (UnitDimension.LENGTH, 0.001),
    "millimeter": (UnitDimension.LENGTH, 0.001),
    "in": (UnitDimension.LENGTH, 0.0254),
    "inch": (UnitDimension.LENGTH, 0.0254),
    "pt": (UnitDimension.LENGTH, PT_TO_M_FACTOR),
    "point": (UnitDimension.LENGTH, PT_TO_M_FACTOR),

    # Area -> square meters (m2)
    "m2": (UnitDimension.AREA, 1.0),
    "sqm": (UnitDimension.AREA, 1.0),
    "cm2": (UnitDimension.AREA, 1e-4),
    "mm2": (UnitDimension.AREA, 1e-6),

    # Volume -> cubic meters (m3)
    "m3": (UnitDimension.VOLUME, 1.0),
    "cbm": (UnitDimension.VOLUME, 1.0),
    "cm3": (UnitDimension.VOLUME, 1e-6),
    "mm3": (UnitDimension.VOLUME, 1e-9),
    "l": (UnitDimension.VOLUME, 1e-3),
    "liter": (UnitDimension.VOLUME, 1e-3),

    # Mass -> kilograms (kg)
    "kg": (UnitDimension.MASS, 1.0),
    "kilogram": (UnitDimension.MASS, 1.0),
    "g": (UnitDimension.MASS, 0.001),
    "gram": (UnitDimension.MASS, 0.001),
    "t": (UnitDimension.MASS, 1000.0),
    "ton": (UnitDimension.MASS, 1000.0),

    # Piece count
    "piece": (UnitDimension.COUNT, 1.0),
    "pc": (UnitDimension.COUNT, 1.0),
    "db": (UnitDimension.COUNT, 1.0),  # Hungarian 'darab'
}


def normalize_unit_str(unit: str) -> str:
    """Normalize unit string representation."""
    cleaned = unit.strip().lower()
    mapping = {
        "m²": "m2",
        "m³": "m3",
        "cm²": "cm2",
        "mm²": "mm2",
        "darab": "piece",
        "db": "piece",
        "pc": "piece",
        "pcs": "piece",
    }
    return mapping.get(cleaned, cleaned)


def get_unit_dimension(unit: str) -> UnitDimension:
    """Return the physical dimension of a unit."""
    norm = normalize_unit_str(unit)
    if norm not in UNIT_FACTORS:
        raise UnitConversionError(f"Unsupported unit: '{unit}'")
    return UNIT_FACTORS[norm][0]


def convert_to_si(value: float, from_unit: str) -> tuple[float, str]:
    """Convert a value from the specified unit to canonical SI base unit.

    Returns:
        tuple[float, str]: (value_in_si, canonical_si_unit_name)
    """
    norm = normalize_unit_str(from_unit)
    if norm not in UNIT_FACTORS:
        raise UnitConversionError(f"Cannot convert unknown unit '{from_unit}' to SI")
    dimension, factor = UNIT_FACTORS[norm]
    canonical_si = SI_BASE_UNITS[dimension]
    return value * factor, canonical_si


def convert_from_si(value_si: float, to_unit: str) -> float:
    """Convert a canonical SI base value to the requested target unit."""
    norm = normalize_unit_str(to_unit)
    if norm not in UNIT_FACTORS:
        raise UnitConversionError(f"Cannot convert from SI to unknown unit '{to_unit}'")
    _, factor = UNIT_FACTORS[norm]
    if factor == 0:
        raise UnitConversionError(f"Invalid zero conversion factor for unit '{to_unit}'")
    return value_si / factor


def convert_units(value: float, from_unit: str, to_unit: str) -> float:
    """Convert value between two compatible units.

    Raises:
        UnitConversionError: If units are incompatible (e.g. length to area) or unknown.
    """
    from_norm = normalize_unit_str(from_unit)
    to_norm = normalize_unit_str(to_unit)

    if from_norm not in UNIT_FACTORS:
        raise UnitConversionError(f"Source unit '{from_unit}' is unknown")
    if to_norm not in UNIT_FACTORS:
        raise UnitConversionError(f"Target unit '{to_unit}' is unknown")

    dim_from, factor_from = UNIT_FACTORS[from_norm]
    dim_to, factor_to = UNIT_FACTORS[to_norm]

    if dim_from != dim_to:
        raise UnitConversionError(
            f"Incompatible unit conversion: cannot convert '{from_unit}' ({dim_from}) "
            f"to '{to_unit}' ({dim_to})"
        )

    val_si = value * factor_from
    return val_si / factor_to
