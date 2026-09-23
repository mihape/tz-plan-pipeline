"""Quantity domain model for deterministic takeoff quantities and input provenance."""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

from tz_plan_pipeline.models.enums import CalculationMethod, Unit


class QuantityInput(BaseModel):
    """Snapshot of an input measurement used in a quantity calculation."""
    measurement_id: UUID = Field(description="UUID of the source Measurement")
    measurement_name: str = Field(description="Property name of the source measurement")
    recorded_value: float = Field(description="Numeric value captured at calculation time")
    recorded_unit: Unit = Field(description="Physical unit of the input measurement")
    is_valid: bool = Field(default=True, description="Whether this input remains valid")
    invalidation_reason: Optional[str] = Field(default=None, description="Reason if marked invalid")


class Quantity(BaseModel):
    """Represents a calculated quantity takeoff item.

    Enforces Non-Negotiable Principles:
    - Principle 1: AI interprets documents but must not serve as the authoritative calculation engine.
    - Principle 2: All final quantities must be calculated by deterministic, testable Python code.
    - Input Tracking: Every quantity tracks its inputs, their snapshots, and validity state.
    """
    id: UUID = Field(default_factory=uuid4, description="Unique quantity UUID")
    project_id: UUID = Field(description="Parent Project UUID")
    element_id: Optional[UUID] = Field(
        default=None,
        description="Associated BuildingElement UUID, or None if aggregated project-level quantity"
    )
    name: str = Field(min_length=1, description="Quantity metric name (e.g. 'net_facade_area_m2')")
    value: float = Field(description="Final calculated numerical quantity")
    unit: Unit = Field(description="Unit of the final quantity")
    calculation_method: CalculationMethod = Field(
        default=CalculationMethod.DETERMINISTIC_FORMULA,
        description="Deterministic calculation method or recorded manual override"
    )
    formula_expression: str = Field(
        min_length=1,
        description="Deterministic formula representation (e.g. 'gross_area - sum(opening_areas)')"
    )
    inputs: list[QuantityInput] = Field(
        default_factory=list,
        description="Snapshot of all input measurements used in this calculation"
    )
    needs_recalculation: bool = Field(
        default=False,
        description="Flagged True if an input measurement has been superseded, modified, or invalidated"
    )
    calculated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when calculation was performed (UTC)"
    )

    def mark_for_recalculation(self, reason: str) -> None:
        """Flag this quantity as requiring recalculation."""
        self.needs_recalculation = True
