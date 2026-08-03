"""Global Pytest Fixtures for Unit & Integration Test Suite."""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.control_plane.main import app


@pytest.fixture(autouse=True)
def mock_provider_api_keys(monkeypatch):
    """Automatically sets mock provider API keys for offline unit test execution."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "mock-test-key-for-unit-testing")
    monkeypatch.setenv("OPENAI_API_KEY", "mock-test-key-for-unit-testing")
    monkeypatch.setenv("GEMINI_API_KEY", "mock-test-key-for-unit-testing")


@pytest.fixture
def test_client():
    """Returns a TestClient instance for testing FastAPI endpoints."""
    return TestClient(app)


@pytest.fixture
def mock_orchestrator():
    """Returns an AsyncMock instance for SandboxOrchestrator."""
    orchestrator = AsyncMock()
    orchestrator.k8s_client_configured = False
    return orchestrator


@pytest.fixture
def mock_dispatcher():
    """Returns an AsyncMock instance for LocalToolDispatcher."""
    dispatcher = AsyncMock()
    dispatcher.dispatch_tool_call.return_value = {
        "status": "SUCCESS",
        "output": "Mock tool output",
    }
    return dispatcher
