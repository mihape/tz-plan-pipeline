"""Replaceable AI Provider Interface for TZ Plan Pipeline.

Enforces Non-Negotiable Principle 8: AI models must be replaceable through a provider interface.
Enforces Non-Negotiable Principle 1: AI interprets documents but must not serve as the authoritative calculation engine.
Zero coupling: No vendor-specific SDK (OpenAI, Anthropic, Google) is imported by the core pipeline.
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Optional
from pydantic import BaseModel, Field

from tz_plan_pipeline.core.errors import AIProviderError


class AIRequest(BaseModel):
    """Agnostic payload submitted to an AI provider."""
    prompt: str = Field(min_length=1, description="Task instruction prompt")
    system_prompt: Optional[str] = Field(default=None, description="System instruction")
    task_type: str = Field(default="interpretation", description="Task category (e.g. 'table_extraction')")
    context: dict[str, Any] = Field(default_factory=dict, description="Domain context data")
    image_bytes: Optional[bytes] = Field(default=None, description="Optional raster drawing crop bytes")
    image_path: Optional[str] = Field(default=None, description="Optional path to drawing image")
    schema_definition: Optional[dict[str, Any]] = Field(
        default=None,
        description="Optional expected JSON schema for structured interpretation"
    )


class AIResponse(BaseModel):
    """Agnostic response returned by an AI provider."""
    raw_text: str = Field(description="Raw text output from model")
    structured_data: Optional[dict[str, Any]] = Field(
        default=None,
        description="Parsed structured data if schema extraction was requested"
    )
    provider_name: str = Field(description="Identifier of the executing provider (e.g. 'mock', 'local_vllm')")
    model_name: str = Field(description="Model identifier (e.g. 'mock-model-v1')")
    confidence_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Hypothesis confidence score. NOTE: Never treated as proof of verification."
    )
    token_usage: dict[str, int] = Field(default_factory=dict, description="Input and output token counts")
    latency_seconds: float = Field(default=0.0, ge=0.0)


class AIProvider(ABC):
    """Abstract interface that all AI providers must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider name."""
        pass

    @abstractmethod
    def process(self, request: AIRequest) -> AIResponse:
        """Process an interpretation request synchronously."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Verify provider availability and operational health."""
        pass


class AIProviderRegistry:
    """Registry allowing dynamic discovery and decoupling of AI providers."""

    def __init__(self):
        self._providers: dict[str, Callable[[], AIProvider]] = {}

    def register(self, name: str, factory: Callable[[], AIProvider]) -> None:
        """Register a provider factory."""
        self._providers[name.lower()] = factory

    def get(self, name: str) -> AIProvider:
        """Instantiate and return the requested provider."""
        key = name.lower()
        if key not in self._providers:
            available = ", ".join(self._providers.keys()) or "None"
            raise AIProviderError(
                f"AI Provider '{name}' is not registered. Available providers: [{available}]"
            )
        return self._providers[key]()

    def list_available(self) -> list[str]:
        """List all registered provider names."""
        return list(self._providers.keys())


# Global singleton registry
provider_registry = AIProviderRegistry()
