"""Integration tests for MVCP LLM Proxy authentication and routing flow."""

import json
import secrets

import litellm
import pytest

from src.control_plane.dependencies import get_auth_service, get_llm_client
from src.control_plane.services.auth_service import AuthService, hash_key
from src.control_plane.services.llm_router import LiteLLMClient


@pytest.fixture
def setup_test_keys_file(tmp_path, monkeypatch, app):
    """Sets up a temporary keys.json file and registers fresh AuthService with FastAPI DI."""
    raw_api_key = "arm_dev_integration_test_key_12345"

    salt = secrets.token_hex(16)
    key_hashed = hash_key(raw_api_key, salt)

    keys_data = {
        "keys": [
            {
                "key_id": "key_dev_test123",
                "name": "integration-test-key",
                "role": "dev",
                "scopes": ["compiler", "autotuner"],
                "salt": salt,
                "hash": key_hashed,
                "created_at": "2026-08-05T00:00:00+00:00",
                "status": "active",
            }
        ]
    }

    temp_keys_file = tmp_path / "keys.json"
    temp_keys_file.write_text(json.dumps(keys_data))

    monkeypatch.setenv("KEYS_FILE_PATH", str(temp_keys_file))

    fresh_auth_service = AuthService(config_path=temp_keys_file)

    # Clean DI Override replacing previous module-level monkeypatching
    app.dependency_overrides[get_auth_service] = lambda: fresh_auth_service

    yield raw_api_key

    app.dependency_overrides.pop(get_auth_service, None)


def test_llm_proxy_success_flow(
    app, test_client, setup_test_keys_file, monkeypatch
):
    """Verifies valid request passes auth and returns expected LLM response with telemetry headers."""
    api_key = setup_test_keys_file

    # Force using real LiteLLMClient wrapper to exercise litellm.acompletion monkeypatch
    app.dependency_overrides[get_llm_client] = lambda: LiteLLMClient()

    # Mock LiteLLM at integration boundary returning realistic ModelResponse
    async def mock_acompletion(*args, **kwargs):
        return litellm.ModelResponse(
            **{
                "id": "chatcmpl-test-999",
                "model": "openai/gpt-4o",
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

    def mock_completion_cost(*args, **kwargs):
        return 0.00025

    monkeypatch.setattr(litellm, "acompletion", mock_acompletion)
    monkeypatch.setattr(litellm, "completion_cost", mock_completion_cost)

    payload = {
        "model": "openai/gpt-4o",
        "messages": [
            {"role": "user", "content": "Test prompt for integration test"}
        ],
        "temperature": 0.7,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
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


def test_llm_proxy_missing_auth_header(test_client):
    """Verifies request without Authorization header returns 401 Unauthorized."""
    payload = {
        "model": "openai/gpt-4o",
        "messages": [{"role": "user", "content": "Unauthenticated test"}],
    }

    response = test_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 401


def test_llm_proxy_invalid_api_key(test_client, setup_test_keys_file):
    """Verifies request with invalid API key returns 401 Unauthorized."""
    payload = {
        "model": "openai/gpt-4o",
        "messages": [{"role": "user", "content": "Invalid key test"}],
    }

    headers = {"Authorization": "Bearer arm_dev_invalid_key_99999"}

    response = test_client.post(
        "/v1/chat/completions", json=payload, headers=headers
    )
    assert response.status_code == 401
