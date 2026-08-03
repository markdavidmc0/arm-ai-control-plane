"""Unit Test Suite for Zero-Trust Auth, Key Management & Keycloak M2M JWT Validation.

Verifies `/api/v1/internal/auth-check` Envoy `ext_authz` sidecar check,
salted SHA-256 key matching, Keycloak OAuth2 token issuance, and M2M tool registration.
"""

from fastapi.testclient import TestClient

from src.control_plane.main import app
from src.control_plane.services.auth_service import AuthService, hash_key

client = TestClient(app)


def test_auth_check_missing_headers():
    """Verify auth-check fails with 401 when no key headers are provided."""
    response = client.get("/api/v1/internal/auth-check")
    assert response.status_code == 401
    assert response.json()["status"] == "DENIED"


def test_auth_check_judge_key_success():
    """Verify X-Judge-API-Key approves instant access and returns user headers."""
    response = client.get(
        "/api/v1/internal/auth-check", headers={"X-Judge-API-Key": "judge_secret_key_123"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"
    assert response.headers["X-User-Role"] == "judge"


def test_auth_check_bearer_key_success():
    """Verify Authorization: Bearer arm_dev_* key approves developer access."""
    response = client.get(
        "/api/v1/internal/auth-check",
        headers={"Authorization": "Bearer arm_dev_local_test_key_123"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"
    scopes_header = response.headers["X-User-Scopes"]
    assert "compiler" in scopes_header
    assert "autotuner" not in scopes_header
    assert "heatmap" not in scopes_header


def test_auth_check_invalid_key():
    """Verify invalid key returns 401 Unauthorized."""
    response = client.get(
        "/api/v1/internal/auth-check", headers={"Authorization": "Bearer arm_invalid_token_999"}
    )
    assert response.status_code == 401
    assert response.json()["status"] == "DENIED"


def test_salted_hash_computation():
    """Verify salted SHA-256 hash algorithm determinism."""
    digest1 = hash_key("test_key_abc", "salt1")
    digest2 = hash_key("test_key_abc", "salt1")
    digest3 = hash_key("test_key_abc", "salt2")

    assert digest1 == digest2
    assert digest1 != digest3
    assert len(digest1) == 64


def test_auth_service_rate_limiting():
    """Verify sliding-window rate limiter blocks after threshold is exceeded."""
    service = AuthService()
    test_id = "test_client_key_123"

    for _ in range(60):
        allowed, _ = service.check_rate_limit(test_id, role="judge")
        assert allowed is True

    allowed, count = service.check_rate_limit(test_id, role="judge")
    assert allowed is False
    assert count == 60


def test_keycloak_token_issuance_success():
    """Verify Keycloak M2M token endpoint returns OAuth2 JWT access token."""
    response = client.post(
        "/realms/arm-platform/protocol/openid-connect/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "github-ci-runner",
            "client_secret": "mcp_ci_runner_secret_2026",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] == 900


def test_keycloak_m2m_tool_registration_success():
    """Verify submitting domain-sliced tool payload using Keycloak Bearer JWT returns 200 OK."""
    token_res = client.post(
        "/realms/arm-platform/protocol/openid-connect/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "github-ci-runner",
            "client_secret": "mcp_ci_runner_secret_2026",
        },
    )
    access_token = token_res.json()["access_token"]

    payload = {
        "tools": [
            {
                "name": "vllm_arm_kv_cache_allocator_analyzer",
                "description": "Analyzes vLLM KV Cache allocation efficiency on Neoverse N2",
                "language": "python",
                "domain": "cloud-ai",
                "parameters": {"type": "object", "properties": {}},
            }
        ]
    }

    reg_res = client.post(
        "/api/v1/registry/register",
        json=payload,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert reg_res.status_code == 200
    assert reg_res.json()["status"] == "SUCCESS"
    assert reg_res.json()["registered_count"] == 1


def test_m2m_tool_registration_invalid_token():
    """Verify registration fails with HTTP 401 when an invalid JWT is provided."""
    payload = {
        "tools": [
            {
                "name": "invalid_tool",
                "domain": "cloud-ai",
                "parameters": {},
            }
        ]
    }

    response = client.post(
        "/api/v1/registry/register",
        json=payload,
        headers={"Authorization": "Bearer invalid_expired_jwt_token_999"},
    )
    assert response.status_code == 401
