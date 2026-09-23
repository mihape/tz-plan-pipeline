"""Unit tests for the replaceable AI provider interface and registry."""

import pytest
from tz_plan_pipeline.ai import AIRequest, AIResponse, MockAIProvider, provider_registry
from tz_plan_pipeline.core.errors import AIProviderError


def test_mock_ai_provider_processing():
    provider = MockAIProvider()
    assert provider.name == "mock"
    assert provider.health_check() is True

    req = AIRequest(
        prompt="Analyze ground floor window callouts",
        context={"project_id": "test-123"}
    )
    resp = provider.process(req)

    assert isinstance(resp, AIResponse)
    assert resp.provider_name == "mock"
    assert resp.model_name == "mock-architectural-vision-v1"
    assert resp.structured_data is not None
    assert "proposals" in resp.structured_data
    assert resp.confidence_score == 0.95
    assert resp.token_usage["total_tokens"] > 0


def test_provider_registry_lookup():
    provider = provider_registry.get("mock")
    assert isinstance(provider, MockAIProvider)

    with pytest.raises(AIProviderError, match="AI Provider 'unknown_vendor' is not registered"):
        provider_registry.get("unknown_vendor")
