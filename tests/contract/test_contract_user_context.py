"""Contract tests for Envoy Edge Guard pre-authenticated UserContext dependency interface."""

import pytest
from fastapi import Depends, FastAPI, status
from fastapi.testclient import TestClient

from src.control_plane.dependencies import UserContext, get_user_context

app = FastAPI()


@app.get("/test-user-context")
async def sample_route(user: UserContext = Depends(get_user_context)):
    """Sample endpoint for validating get_user_context header extraction."""
    return {"user_id": user.user_id, "role": user.role, "scopes": user.scopes}


client = TestClient(app)


@pytest.mark.contract
def test_user_context_valid_headers():
    """Verify get_user_context parses downstream Envoy identity headers correctly."""
    headers = {
        "X-User-ID": "usr_99",
        "X-User-Role": "admin",
        "X-User-Scopes": "read, write",
    }
    response = client.get("/test-user-context", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "user_id": "usr_99",
        "role": "admin",
        "scopes": ["read", "write"],
    }


@pytest.mark.contract
def test_user_context_default_fallbacks():
    """Verify get_user_context sets default role and empty scopes when headers are missing."""
    headers = {"X-User-ID": "usr_42"}
    response = client.get("/test-user-context", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "user_id": "usr_42",
        "role": "user",
        "scopes": [],
    }


@pytest.mark.contract
def test_user_context_empty_or_whitespace_scopes():
    """Verify get_user_context correctly handles empty strings and trailing commas in scopes."""
    headers = {
        "X-User-ID": "usr_42",
        "X-User-Scopes": "read, , write , ",
    }
    response = client.get("/test-user-context", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["scopes"] == ["read", "write"]


@pytest.mark.contract
def test_user_context_missing_x_user_id():
    """Verify get_user_context enforces HTTP 401 when X-User-ID header is missing."""
    response = client.get("/test-user-context")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Missing upstream identity header" in response.json()["detail"]
