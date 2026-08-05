"""Unit Tests for Control Plane AuthService & Keycloak JWT Verification."""

import base64
import json
import time
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from src.control_plane.dependencies import verify_authentication
from src.control_plane.services.auth_service import AuthService, hash_key


@pytest.mark.unit
def test_hash_key_deterministic_output():
    """Verify hash_key produces deterministic salted SHA-256 digests."""
    digest1 = hash_key("my_secret_key_123", salt="mvcp_salt_2026")
    digest2 = hash_key("my_secret_key_123", salt="mvcp_salt_2026")
    digest_different_salt = hash_key("my_secret_key_123", salt="custom_salt_999")

    assert len(digest1) == 64
    assert digest1 == digest2
    assert digest1 != digest_different_salt


@pytest.mark.unit
def test_auth_service_verify_key_valid_and_invalid():
    """Verify verify_key validates active keys and rejects invalid or missing keys."""
    auth_service = AuthService()

    # Valid fallback keys
    judge_record = auth_service.verify_key("judge_secret_key_123")
    assert judge_record is not None
    assert judge_record.get("role") == "judge"

    dev_record = auth_service.verify_key("arm_dev_local_test_key_123")
    assert dev_record is not None
    assert dev_record.get("role") == "dev"

    # Invalid / Missing keys
    assert auth_service.verify_key("invalid_random_key_999") is None
    assert auth_service.verify_key("") is None
    assert auth_service.verify_key(None) is None


@pytest.mark.unit
def test_auth_service_check_rate_limit():
    """Verify check_rate_limit enforces sliding-window rate limits per role."""
    auth_service = AuthService()
    key_id = "test_judge_key_001"

    # Judge role limit is 60 requests/minute
    for _ in range(60):
        allowed, count = auth_service.check_rate_limit(key_id, role="judge")
        assert allowed is True

    # 61st request must be rate limited
    allowed_over_limit, count_over = auth_service.check_rate_limit(key_id, role="judge")
    assert allowed_over_limit is False
    assert count_over == 60


@pytest.mark.unit
def test_auth_service_mint_and_verify_jwt():
    """Verify mint_keycloak_jwt generates a valid JWT token verified by verify_jwt_token."""
    auth_service = AuthService()

    jwt_token = auth_service.mint_keycloak_jwt(
        grant_type="client_credentials", client_id="github-ci-runner"
    )
    assert jwt_token.count(".") == 2

    # Verify directly via verify_jwt_token
    payload = auth_service.verify_jwt_token(jwt_token)
    assert payload is not None
    assert payload.get("azp") == "github-ci-runner"
    assert "https://keycloak.internal" in payload.get("iss", "")

    # Verify via verify_key and check dynamic scope resolution
    record = auth_service.verify_key(f"Bearer {jwt_token}")
    assert record is not None
    assert record.get("role") == "m2m"
    assert record.get("scopes") == ["tools:register", "profile", "email"]


@pytest.mark.unit
def test_auth_service_expired_jwt_rejection():
    """Verify verify_jwt_token rejects expired JWT tokens."""
    auth_service = AuthService()

    past_time = int(time.time()) - 3600
    hdr = json.dumps({"alg": "RS256"}).encode()
    header_b64 = base64.urlsafe_b64encode(hdr).decode().rstrip("=")

    pld = json.dumps({
        "exp": past_time,
        "iss": "https://keycloak.internal/realms/arm-platform",
        "azp": "github-ci-runner",
        "scope": "tools:register",
    }).encode()
    payload_b64 = base64.urlsafe_b64encode(pld).decode().rstrip("=")

    expired_jwt = f"{header_b64}.{payload_b64}.mock_sig"
    assert auth_service.verify_jwt_token(expired_jwt) is None


@pytest.mark.unit
def test_auth_service_invalid_issuer_jwt_rejection():
    """Verify verify_jwt_token rejects JWT tokens with unknown issuers."""
    auth_service = AuthService()

    future_time = int(time.time()) + 3600
    hdr = json.dumps({"alg": "RS256"}).encode()
    header_b64 = base64.urlsafe_b64encode(hdr).decode().rstrip("=")

    pld = json.dumps({
        "exp": future_time,
        "iss": "https://untrusted-issuer.com/auth",
        "azp": "github-ci-runner",
        "scope": "tools:register",
    }).encode()
    payload_b64 = base64.urlsafe_b64encode(pld).decode().rstrip("=")

    invalid_iss_jwt = f"{header_b64}.{payload_b64}.mock_sig"
    assert auth_service.verify_jwt_token(invalid_iss_jwt) is None


@pytest.mark.unit
def test_auth_service_missing_role_jwt_rejection():
    """Verify verify_jwt_token rejects Keycloak tokens lacking required client_id/role/scope."""
    auth_service = AuthService()

    future_time = int(time.time()) + 3600
    hdr = json.dumps({"alg": "RS256"}).encode()
    header_b64 = base64.urlsafe_b64encode(hdr).decode().rstrip("=")

    pld = json.dumps({
        "exp": future_time,
        "iss": "https://keycloak.internal/realms/arm-platform",
        "azp": "unauthorized-client",
        "client_id": "unauthorized-client",
        "realm_access": {"roles": ["default-user"]},
        "scope": "profile email",
    }).encode()
    payload_b64 = base64.urlsafe_b64encode(pld).decode().rstrip("=")

    unauthorized_jwt = f"{header_b64}.{payload_b64}.mock_sig"
    assert auth_service.verify_jwt_token(unauthorized_jwt) is None


@pytest.mark.unit
@pytest.mark.unauthenticated
@pytest.mark.asyncio
async def test_verify_authentication_dependency_missing_header():
    """Verify verify_authentication dependency raises 401 when auth header is missing."""
    mock_auth_service = MagicMock(spec=AuthService)

    with pytest.raises(HTTPException) as exc_info:
        await verify_authentication(
            authorization=None,
            auth_service=mock_auth_service,
        )

    assert exc_info.value.status_code == 401
    assert "Missing or invalid Authorization header" in exc_info.value.detail


@pytest.mark.unit
@pytest.mark.unauthenticated
@pytest.mark.asyncio
async def test_verify_authentication_dependency_valid_header():
    """Verify verify_authentication dependency extracts bearer key and calls auth service."""
    mock_auth_service = MagicMock(spec=AuthService)
    mock_auth_service.verify_key.return_value = {"key_id": "k123", "role": "dev"}

    result = await verify_authentication(
        authorization="Bearer valid_test_key_123",
        auth_service=mock_auth_service,
    )

    assert result == {"key_id": "k123", "role": "dev"}
    mock_auth_service.verify_key.assert_called_once_with("valid_test_key_123")
