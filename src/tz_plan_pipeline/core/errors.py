"""Domain exception hierarchy for TZ Plan Pipeline."""

from typing import Any, Optional


class TZPipelineError(Exception):
    """Base exception for all errors within TZ Plan Pipeline."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class MissingDataError(TZPipelineError):
    """Raised when a required measurement or attribute is missing (None).

    Enforces Non-Negotiable Principle 5: Missing data must never silently become zero.
    """
    pass


class DocumentImmutabilityError(TZPipelineError):
    """Raised when document integrity verification fails or an attempt to modify an immutable plan occurs.

    Enforces Non-Negotiable Principle 11: Original project documents must remain immutable.
    """
    pass


class ApprovalSimulationError(TZPipelineError):
    """Raised when an automated agent or non-human entity attempts to execute an authoritative approval.

    Enforces Non-Negotiable Principle 10: User approval must not be simulated by an AI agent.
    """
    pass


class ProvenanceError(TZPipelineError):
    """Raised when measurement lacks required evidence links or contains invalid provenance references.

    Enforces Non-Negotiable Principle 3: Every extracted measurement must retain its original source.
    """
    pass


class ConflictingEvidenceError(TZPipelineError):
    """Raised when conflicting evidence sources are detected without resolution.

    Enforces Non-Negotiable Principle 7: Conflicting source data must create a review item.
    """
    pass


class UncalibratedScaleError(TZPipelineError):
    """Raised when attempting to convert drawing coordinates to authoritative real-world measurements

    using an uncalibrated, unverified, or failed scale.
    Printed scale labels (e.g. 1:50) must not be treated as authoritative geometry without calibration.
    """
    pass


class ScaleCalibrationError(TZPipelineError):
    """Raised when scale calibration fails tolerance checks."""
    pass


class UnitConversionError(TZPipelineError):
    """Raised when an invalid or incompatible unit conversion is requested."""
    pass


class ConfigurationError(TZPipelineError):
    """Raised when application or project configuration is invalid or missing."""
    pass


class StorageError(TZPipelineError):
    """Raised when SQLite storage operations or migrations fail."""
    pass


class AIProviderError(TZPipelineError):
    """Raised when an AI provider fails during inference or schema extraction."""
    pass
