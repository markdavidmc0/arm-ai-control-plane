"""Unit test suite fixtures and global mocks."""

import pytest

from src.control_plane.dependencies import UserContext, get_user_context


@pytest.fixture(autouse=True)
def mock_auth_bypass(request: pytest.FixtureRequest, app):
    """Automatically bypasses authentication for all unit tests.

    To test auth failure cases (e.g. 401 status codes), mark the test function with:
    `@pytest.mark.unauthenticated`
    """
    if "unauthenticated" in request.keywords:
        yield
        return

    app.dependency_overrides[get_user_context] = lambda: UserContext(
        user_id="unit-test-user-001",
        role="admin",
        scopes=["llm:proxy", "tools:register"],
    )
    yield
    app.dependency_overrides.pop(get_user_context, None)


@pytest.fixture(autouse=True)
def set_unit_test_env(monkeypatch: pytest.MonkeyPatch):
    """Set standard default environment variables across unit tests."""
    monkeypatch.setenv("GCP_PROJECT_ID", "test-gcp-project")
    monkeypatch.setenv("GCP_LOCATION", "us-central1")
