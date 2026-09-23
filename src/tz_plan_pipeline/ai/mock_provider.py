"""Deterministic Mock AI Provider for testing and offline operation."""

import time
from typing import Any, Optional
from tz_plan_pipeline.ai.provider import AIProvider, AIRequest, AIResponse, provider_registry


class MockAIProvider(AIProvider):
    """Deterministic, zero-dependency AI provider for testing and offline execution."""

    def __init__(
        self,
        default_response_text: str = "Mock AI interpretation completed.",
        mock_structured_data: Optional[dict[str, Any]] = None,
        confidence: float = 0.95
    ):
        self._default_text = default_response_text
        self._mock_structured_data = mock_structured_data or {
            "elements_identified": 1,
            "proposals": [
                {
                    "element_tag": "NY-01",
                    "element_type": "opening_window",
                    "proposed_width": 1.50,
                    "proposed_height": 1.50,
                    "unit": "m",
                    "confidence": confidence
                }
            ]
        }
        self._confidence = confidence

    @property
    def name(self) -> str:
        return "mock"

    def process(self, request: AIRequest) -> AIResponse:
        start_time = time.perf_counter()
        latency = time.perf_counter() - start_time

        return AIResponse(
            raw_text=self._default_text,
            structured_data=self._mock_structured_data,
            provider_name=self.name,
            model_name="mock-architectural-vision-v1",
            confidence_score=self._confidence,
            token_usage={"prompt_tokens": 120, "completion_tokens": 45, "total_tokens": 165},
            latency_seconds=latency
        )

    def health_check(self) -> bool:
        return True


# Register mock provider by default
provider_registry.register("mock", lambda: MockAIProvider())
