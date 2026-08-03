"""Global Pytest Fixtures for Unit & Integration Test Suite."""

import pytest


@pytest.fixture(autouse=True)
def mock_provider_api_keys(monkeypatch):
    """Automatically sets mock provider API keys for offline unit test execution."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "mock-test-key-for-unit-testing")
    monkeypatch.setenv("OPENAI_API_KEY", "mock-test-key-for-unit-testing")
    monkeypatch.setenv("GEMINI_API_KEY", "mock-test-key-for-unit-testing")
