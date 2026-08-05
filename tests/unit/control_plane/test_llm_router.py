"""Unit Tests for Control Plane LLMRouterService & Telemetry Header Injection."""

import litellm
import pytest

from src.control_plane.dependencies import get_llm_router_service
from src.control_plane.services.llm_router import LiteLLMClient, LLMRouterService


@pytest.mark.asyncio
async def test_llm_router_service_route_completion(monkeypatch):
    """Verify LLMRouterService routes completion and returns 5 telemetry headers."""

    async def mock_acompletion(*args, **kwargs):
        return litellm.ModelResponse(
            **{
                "id": "chatcmpl-test",
                "model": "claude-3-5-sonnet",
                "choices": [
                    {"message": {"role": "assistant", "content": "Hello human"}}
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8},
            }
        )

    monkeypatch.setattr(litellm, "acompletion", mock_acompletion)

    # Inject LiteLLMClient so service delegates execution to litellm.acompletion
    service = LLMRouterService(llm_client=LiteLLMClient())
    request_data = {
        "model": "claude-3-5-sonnet",
        "messages": [{"role": "user", "content": "Hello LLM"}],
        "temperature": 0.7,
    }

    payload, headers = await service.route_completion(request_data)

    assert "choices" in payload
    assert len(payload["choices"]) > 0

    # Verify all 5 required telemetry headers are present
    assert "X-LLM-Cost-USD" in headers
    assert "X-LLM-Prompt-Tokens" in headers
    assert "X-LLM-Completion-Tokens" in headers
    assert "X-LLM-Latency-MS" in headers
    assert "X-LLM-Provider" in headers

    assert float(headers["X-LLM-Latency-MS"]) >= 0
    assert headers["X-LLM-Prompt-Tokens"] == "12"


@pytest.mark.unit
def test_llm_proxy_router_endpoint(app, test_client):
    """Verify POST /v1/chat/completions injects telemetry headers into HTTP response."""

    class MockLLMRouterService:
        async def route_completion(self, request_data):
            return {"choices": []}, {
                "X-LLM-Cost-USD": "0.000100",
                "X-LLM-Prompt-Tokens": "10",
                "X-LLM-Completion-Tokens": "20",
                "X-LLM-Latency-MS": "45.2",
                "X-LLM-Provider": "gpt-4o",
            }

    # Auth bypass is handled automatically by unit/conftest.py mock_auth_bypass fixture
    app.dependency_overrides[get_llm_router_service] = lambda: MockLLMRouterService()

    request_data = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "Test proxy"}],
    }

    response = test_client.post(
        "/v1/chat/completions",
        json=request_data,
        headers={"Authorization": "Bearer test-api-key"},
    )

    # Clean up ONLY the specific service override to prevent wiping fixture overrides
    app.dependency_overrides.pop(get_llm_router_service, None)

    assert response.status_code == 200
    assert "X-LLM-Cost-USD" in response.headers
    assert "X-LLM-Prompt-Tokens" in response.headers
    assert "X-LLM-Completion-Tokens" in response.headers
    assert "X-LLM-Latency-MS" in response.headers
    assert "X-LLM-Provider" in response.headers


@pytest.mark.unauthenticated
def test_llm_proxy_router_endpoint_unauthorized(test_client):
    """Verify POST /v1/chat/completions returns 401 when auth is not bypassed."""
    request_data = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "Test unauthorized"}],
    }
    response = test_client.post("/v1/chat/completions", json=request_data)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_llm_router_vertex_ai_configuration(monkeypatch):
    """Verify Vertex AI / Gemini models configure custom_llm_provider and project params."""
    captured_kwargs = {}

    async def mock_acompletion(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return litellm.ModelResponse(
            **{
                "id": "gemini-test-1",
                "model": kwargs.get("model"),
                "choices": [
                    {"message": {"role": "assistant", "content": "Gemini response"}}
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            }
        )

    monkeypatch.setattr(litellm, "acompletion", mock_acompletion)

    # Inject LiteLLMClient to verify parameters passed down to litellm.acompletion
    service = LLMRouterService(llm_client=LiteLLMClient())
    request_data = {
        "model": "vertex_ai/gemini-1.5-pro",
        "messages": [{"role": "user", "content": "Vertex test"}],
    }

    payload, headers = await service.route_completion(request_data)

    assert captured_kwargs.get("custom_llm_provider") == "vertex_ai"
    assert captured_kwargs.get("vertex_project") == "test-gcp-project"
    assert captured_kwargs.get("vertex_location") == "us-central1"
    assert headers["X-LLM-Prompt-Tokens"] == "10"
    assert headers["X-LLM-Completion-Tokens"] == "20"
