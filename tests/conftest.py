"""Global Pytest Fixtures for Unit & Integration Test Suite."""

import os
from typing import Any, Generator
from unittest.mock import AsyncMock

import litellm
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.control_plane.dependencies import get_llm_client
from src.control_plane.main import app as fastapi_app


def pytest_addoption(parser: pytest.Parser) -> None:
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


# --- CLI Option Fixtures ---

@pytest.fixture(scope="session")
def target_env(request: pytest.FixtureRequest) -> str:
    """Returns the target environment CLI flag value."""
    return request.config.getoption("--target")


@pytest.fixture(scope="session")
def gateway_endpoint(request: pytest.FixtureRequest) -> str | None:
    """Returns the gateway endpoint URL CLI flag value."""
    return request.config.getoption("--endpoint")


# --- FastAPI Application & Client Fixtures ---

@pytest.fixture
def app() -> FastAPI:
    """Provides the FastAPI app instance for testing and dependency overrides."""
    return fastapi_app


@pytest.fixture
def test_client(app: FastAPI) -> Generator[TestClient, None, None]:
    """Provides a TestClient instance while properly managing FastAPI lifespan context."""
    with TestClient(app) as client:
        yield client


# --- Global Mocks & Environment Isolation ---

class MockLLMClient:
    """Test double providing deterministic completion responses for offline execution."""

    async def acompletion(self, **kwargs: Any) -> Any:
        model = kwargs.get("model", "claude-3-5-sonnet")
        response_data = {
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
        return litellm.ModelResponse(**response_data)


@pytest.fixture(autouse=True)
def mock_provider_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Automatically sets mock provider API keys for offline unit test execution."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "mock-test-key-for-unit-testing")
    monkeypatch.setenv("OPENAI_API_KEY", "mock-test-key-for-unit-testing")
    monkeypatch.setenv("GEMINI_API_KEY", "mock-test-key-for-unit-testing")


@pytest.fixture(autouse=True)
def mock_llm_execution(
    app: FastAPI,
    mock_provider_api_keys: None,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    """Overrides LLM client dependency and price calculations for offline testing."""
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY", "")
    has_real_keys = bool(
        (anthropic_key and not anthropic_key.startswith("mock-"))
        or (openai_key and not openai_key.startswith("mock-"))
    )

    if not has_real_keys:
        # Override execution client via Dependency Injection container
        app.dependency_overrides[get_llm_client] = lambda: MockLLMClient()

        # Monkeypatch isolated catalog pricing function used within LLMRouterService
        monkeypatch.setattr(litellm, "completion_cost", lambda *args, **kwargs: 0.000123)

        yield

        app.dependency_overrides.pop(get_llm_client, None)
    else:
        yield


@pytest.fixture
def mock_dispatcher() -> AsyncMock:
    """Returns an AsyncMock instance for LocalToolDispatcher."""
    dispatcher = AsyncMock()
    dispatcher.dispatch_tool_call.return_value = {
        "status": "SUCCESS",
        "output": "Mock tool output",
    }
    return dispatcher
