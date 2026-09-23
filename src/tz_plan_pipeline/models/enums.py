"""Domain enumerations for TZ Plan Pipeline."""

from enum import StrEnum


class ValueOrigin(StrEnum):
    """Origin/provenance of a measurement or data point.

    Distinguishes where a value came from.
    """
    EXTRACTED = "extracted"                   # Directly extracted from CAD vectors/text
    INFERRED = "inferred"                     # Inferred deterministically by rules/geometry
    MANUAL_INPUT = "manual_input"             # Entered directly by human user
    MANUALLY_CORRECTED = "manually_corrected" # Corrected replacement for an original measurement
    AI_HYPOTHESIS = "ai_hypothesis"           # Proposed by AI model (unauthoritative candidate)


class VerificationStatus(StrEnum):
    """Lifecycle verification status of a measurement or takeoff claim.

    Strictly separated from ValueOrigin. AI confidence does NOT imply verification.
    """
    UNVERIFIED = "unverified"
    AUTO_VERIFIED = "auto_verified"       # Deterministically verified by cross-check rules
    REVIEW_REQUIRED = "review_required"   # Conflict or uncertainty flagged for human review
    HUMAN_APPROVED = "human_approved"     # Explicitly approved by authenticated human reviewer
    REJECTED = "rejected"                 # Explicitly rejected


class ActorRole(StrEnum):
    """Role of an actor interacting with the system.

    Provides a domain-level approval boundary.
    Only HUMAN_REVIEWER can execute authoritative human approvals.
    """
    HUMAN_REVIEWER = "human_reviewer"
    SYSTEM_RULE = "system_rule"
    AI_AGENT = "ai_agent"


class ElementType(StrEnum):
    """Categories of construction building elements."""
    FACADE_WALL = "facade_wall"
    PLINTH = "plinth"
    OPENING_WINDOW = "opening_window"
    OPENING_DOOR = "opening_door"
    FINISH_FLOOR = "finish_floor"
    FINISH_WALL = "finish_wall"
    FINISH_CEILING = "finish_ceiling"
    MASONRY = "masonry"
    SLAB = "slab"
    ROOF = "roof"
    BEAM_COLUMN = "beam_column"
    OTHER = "other"


class Unit(StrEnum):
    """Supported physical measurement units."""
    M = "m"
    M2 = "m2"
    M3 = "m3"
    MM = "mm"
    CM = "cm"
    PIECE = "piece"
    KG = "kg"


class DocumentType(StrEnum):
    """Types of architectural and engineering project documents."""
    ARCHITECTURAL_PLAN = "architectural_plan"
    ELEVATION = "elevation"
    SECTION = "section"
    OPENING_SCHEDULE = "opening_schedule"
    TECHNICAL_SPEC = "technical_spec"
    SITE_PLAN = "site_plan"
    OTHER = "other"


class EvidenceSourceType(StrEnum):
    """Nature of extracted evidence in drawing documents."""
    CAD_VECTOR = "cad_vector"
    CAD_TEXT = "cad_text"
    OCR_TEXT = "ocr_text"
    RASTER_VISUAL = "raster_visual"
    MANUAL_ANNOTATION = "manual_annotation"
    AI_PROPOSAL = "ai_proposal"


class FindingSeverity(StrEnum):
    """Severity classification for audit findings."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CONFLICT = "conflict"


class ReviewStatus(StrEnum):
    """Status of an audit finding review."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"


class CalculationMethod(StrEnum):
    """Calculation method used for a quantity takeoff."""
    DETERMINISTIC_FORMULA = "deterministic_formula"
    MANUAL_OVERRIDE_RECORDED = "manual_override_recorded"
