"""Global Pytest Fixtures for Unit & Integration Test Suite."""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.control_plane.main import app


def pytest_addoption(parser):
    """Registers custom CLI flags for workflow and target selection."""
    parser.addoption(
        "--target",
        action="store",
        default="inmemory",
        choices=["inmemory", "kind", "live_gke"],
        help="Target environment: inmemory, kind, or live_gke",
    )
    parser.addoption(
        "--endpoint",
        "--gateway-base-url",
        action="store",
        default=None,
        help="HTTP/TCP gateway URL endpoint for cluster environments",
    )
    parser.addoption(
        "--run-benchmarks",
        action="store_true",
        default=False,
        help="Opt-in flag to run heavy live LLM benchmark scenarios",
    )


@pytest.fixture(autouse=True)
def mock_provider_api_keys(monkeypatch):
    """Automatically sets mock provider API keys for offline unit test execution."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "mock-test-key-for-unit-testing")
    monkeypatch.setenv("OPENAI_API_KEY", "mock-test-key-for-unit-testing")
    monkeypatch.setenv("GEMINI_API_KEY", "mock-test-key-for-unit-testing")


@pytest.fixture(autouse=True)
def mock_litellm_completion(monkeypatch):
    """Mocks litellm.acompletion and litellm.completion_cost for offline unit & PR-gate testing."""
    import os

    import litellm

    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY", "")
    has_real_keys = bool(
        (anthropic_key and not anthropic_key.startswith("mock-"))
        or (openai_key and not openai_key.startswith("mock-"))
    )

    if not has_real_keys:

        async def _mock_acompletion(*args, **kwargs):
            model = kwargs.get("model", "claude-3-5-sonnet")
            return {
                "id": "chatcmpl-mock-123",
                "object": "chat.completion",
                "created": 1700000000,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": f"Mock LiteLLM completion response for model [{model}].",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 15,
                    "completion_tokens": 25,
                    "total_tokens": 40,
                },
            }

        def _mock_completion_cost(*args, **kwargs):
            return 0.000123

        monkeypatch.setattr(litellm, "acompletion", _mock_acompletion)
        monkeypatch.setattr(litellm, "completion_cost", _mock_completion_cost)


@pytest.fixture
def test_client():
    """Returns a TestClient instance for testing FastAPI endpoints."""
    return TestClient(app)


@pytest.fixture
def mock_dispatcher():
    """Returns an AsyncMock instance for LocalToolDispatcher."""
    dispatcher = AsyncMock()
    dispatcher.dispatch_tool_call.return_value = {
        "status": "SUCCESS",
        "output": "Mock tool output",
    }
    return dispatcher
