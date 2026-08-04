"""Contract Tests for Auth Router & Envoy ExtAuthz Filter Interface."""

import base64
import json
import time
import pytest


def _create_mock_jwt(payload: dict) -> str:
    """Helper to generate an unsigned mock JWT for contract tests."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "typ": "JWT"}).encode()).decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{header}.{body}.mock_signature"


@pytest.mark.contract
def test_ext_authz_valid_jwt_header_injection(test_client):
    """Test GET /api/v1/internal/auth-check with a valid API key.

    Asserts HTTP 200 OK, response status 'APPROVED', and injected Envoy headers:
    X-User-ID, X-User-Role, X-User-Scopes, and X-Envoy-Auth-Status.
    """
    response = test_client.get(
        "/api/v1/internal/auth-check",
        headers={"x-judge-api-key": "judge_secret_key_123"},
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data.get("status") == "APPROVED"
    assert res_data.get("role") == "judge"

    # Verify injected Envoy response headers for downstream routing
    assert response.headers.get("X-User-ID") == "key_judge_001"
    assert response.headers.get("X-User-Role") == "judge"
    assert "compiler" in response.headers.get("X-User-Scopes", "")
    assert response.headers.get("X-Envoy-Auth-Status") == "APPROVED"


@pytest.mark.contract
def test_ext_authz_valid_bearer_keycloak_jwt_injection(test_client):
    """Test GET /api/v1/internal/auth-check with a valid Keycloak M2M Bearer JWT.

    Asserts HTTP 200 OK, status 'APPROVED', and proper header injection for Envoy.
    """
    mock_payload = {
        "iss": "http://localhost:8080/realms/arm-platform",
        "sub": "service-account-github-ci-runner",
        "client_id": "github-ci-runner",
        "azp": "github-ci-runner",
        "scope": "tools:register profile email",
        "realm_access": {"roles": ["mcp-registrar"]},
    }
    mock_jwt = _create_mock_jwt(mock_payload)

    response = test_client.get(
        "/api/v1/internal/auth-check",
        headers={"Authorization": f"Bearer {mock_jwt}"},
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data.get("status") == "APPROVED"

    # Enforce Envoy ExtAuthz contract headers for JWT users
    assert response.headers.get("X-Envoy-Auth-Status") == "APPROVED"
    assert response.headers.get("X-User-Role") == "m2m"
    assert response.headers.get("X-User-ID") == "service-account-github-ci-runner"
    assert "tools:register" in response.headers.get("X-User-Scopes", "")


@pytest.mark.contract
def test_ext_authz_github_oidc_jwt_injection(test_client):
    """Test GET /api/v1/internal/auth-check with a valid GitHub Actions OIDC token.

    Verifies GitHub OIDC claims validation contract.
    """
    mock_payload = {
        "iss": "https://token.actions.githubusercontent.com",
        "sub": "repo:markdavidmc0/arm-developer-workspace:ref:refs/heads/main",
        "repository": "markdavidmc0/arm-developer-workspace",
    }
    mock_jwt = _create_mock_jwt(mock_payload)

    response = test_client.get(
        "/api/v1/internal/auth-check",
        headers={"Authorization": f"Bearer {mock_jwt}"},
    )
    assert response.status_code == 200
    assert response.headers.get("X-Envoy-Auth-Status") == "APPROVED"


@pytest.mark.contract
def test_ext_authz_expired_jwt_rejection(test_client):
    """Test GET /api/v1/internal/auth-check with an expired Bearer JWT.

    Asserts HTTP 401 Unauthorized and X-Envoy-Auth-Status: DENIED header.
    """
    mock_payload = {
        "exp": int(time.time()) - 3600,  # Expired 1 hour ago
        "iss": "http://localhost:8080/realms/arm-platform",
        "client_id": "github-ci-runner",
    }
    mock_jwt = _create_mock_jwt(mock_payload)

    response = test_client.get(
        "/api/v1/internal/auth-check",
        headers={"Authorization": f"Bearer {mock_jwt}"},
    )
    assert response.status_code == 401
    assert response.headers.get("X-Envoy-Auth-Status") == "DENIED"


@pytest.mark.contract
def test_ext_authz_missing_token_rejection(test_client):
    """Test GET /api/v1/internal/auth-check without authentication headers.

    Asserts HTTP 401 Unauthorized, status 'DENIED', and X-Envoy-Auth-Status header.
    """
    response = test_client.get("/api/v1/internal/auth-check")
    assert response.status_code == 401
    res_data = response.json()
    assert res_data.get("status") == "DENIED"
    assert "Missing API Key" in res_data.get("detail", "")
    assert response.headers.get("X-Envoy-Auth-Status") == "DENIED"


@pytest.mark.contract
def test_keycloak_m2m_oidc_token_issuance(test_client):
    """Test POST /realms/arm-platform/protocol/openid-connect/token with M2M credentials.

    Asserts HTTP 200 OK with Bearer access token payload matching AuthService requirements.
    """
    payload = {
        "grant_type": "client_credentials",
        "client_id": "github-ci-runner",
        "client_secret": "mcp_ci_runner_secret_2026",
    }
    response = test_client.post(
        "/realms/arm-platform/protocol/openid-connect/token",
        data=payload,
    )
    assert response.status_code == 200
    res_data = response.json()
    assert "access_token" in res_data
    assert res_data.get("token_type") == "Bearer"
    assert res_data.get("expires_in") == 900
