"""Integration tests for MVCP LLM Proxy authentication and routing flow."""

import litellm
import pytest

from src.control_plane.dependencies import get_llm_client


class FakeLLMClient:
    """In-memory fake implementing LLMClientProtocol without hitting third-party APIs."""

    async def acompletion(self, **kwargs):
        return litellm.ModelResponse(
            **{
                "id": "chatcmpl-test-999",
                "model": kwargs.get("model", "openai/gpt-4o"),
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "MVCP Integration Test Response",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 10,
                    "total_tokens": 30,
                },
            }
        )


@pytest.fixture
def mock_llm_di(app, monkeypatch):
    """Overrides get_llm_client dependency and patches completion_cost for telemetry."""
    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient()
    monkeypatch.setattr(litellm, "completion_cost", lambda *args, **kwargs: 0.00025)
    yield
    app.dependency_overrides.pop(get_llm_client, None)


def test_llm_proxy_success_flow(test_client, mock_llm_di):
    """Verifies valid request returns expected LLM response and telemetry headers."""
    payload = {
        "model": "openai/gpt-4o",
        "messages": [
            {"role": "user", "content": "Test prompt for integration test"}
        ],
        "temperature": 0.7,
    }

    headers = {
        "X-User-ID": "usr_dev_integration_001",
        "X-User-Role": "dev",
        "X-User-Scopes": "compiler, autotuner",
        "Content-Type": "application/json",
    }

    response = test_client.post(
        "/v1/chat/completions", json=payload, headers=headers
    )

    assert response.status_code == 200

    body = response.json()
    assert (
        body["choices"][0]["message"]["content"]
        == "MVCP Integration Test Response"
    )

    # Telemetry header assertions
    assert "X-LLM-Cost-USD" in response.headers
    assert float(response.headers["X-LLM-Cost-USD"]) == 0.00025

    assert "X-LLM-Prompt-Tokens" in response.headers
    assert response.headers["X-LLM-Prompt-Tokens"] == "20"

    assert "X-LLM-Completion-Tokens" in response.headers
    assert response.headers["X-LLM-Completion-Tokens"] == "10"

    assert "X-LLM-Latency-MS" in response.headers
    assert float(response.headers["X-LLM-Latency-MS"]) >= 0.0

    assert "X-LLM-Provider" in response.headers
    assert response.headers["X-LLM-Provider"] == "openai"


def test_llm_proxy_missing_user_id_header(test_client):
    """Verifies request without X-User-ID header returns 401 Unauthorized."""
    payload = {
        "model": "openai/gpt-4o",
        "messages": [{"role": "user", "content": "Unauthenticated test"}],
    }

    response = test_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 401
    assert "Missing upstream identity header" in response.json()["detail"]
