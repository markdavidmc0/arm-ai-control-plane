"""Unit Test Suite for Zero-Trust Auth & Key Management.

Verifies `/api/v1/internal/auth-check` Envoy `ext_authz` sidecar check,
salted SHA-256 key matching, sliding-window rate limiting, and CLI key management.
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
    assert "compiler" in response.headers["X-User-Scopes"]


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

    # Role 'judge' max limit is 60 req/min
    for _ in range(60):
        allowed, _ = service.check_rate_limit(test_id, role="judge")
        assert allowed is True

    # 61st request must be blocked
    allowed, count = service.check_rate_limit(test_id, role="judge")
    assert allowed is False
    assert count == 60
