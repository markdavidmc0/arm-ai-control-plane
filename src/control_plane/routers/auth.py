"""Auth & Keycloak OIDC APIRouter.

Serves `/api/v1/internal/auth-check` for Envoy `ext_authz` sidecar validation,
and `/realms/arm-platform/protocol/openid-connect/token` for Keycloak M2M OAuth2 tokens.
"""

import base64
import json
import time
from fastapi import APIRouter, Form, Header, Request, Response, status
from pydantic import BaseModel
from src.control_plane.services.auth_service import AuthService

router = APIRouter(tags=["Zero-Trust Auth Guard & Keycloak OIDC"])
auth_service = AuthService()


class TokenRequest(BaseModel):
    grant_type: str = "client_credentials"
    client_id: str | None = None
    client_secret: str | None = None


@router.get("/api/v1/internal/auth-check")
async def envoy_ext_authz_check(
    response: Response,
    x_judge_api_key: str | None = Header(None, alias="x-judge-api-key"),
    authorization: str | None = Header(None, alias="authorization"),
):
    """Sidecar authentication check endpoint called by Envoy proxy.

    Returns:
        HTTP 200 OK with injected `X-User-Role` and `X-User-Scopes` on success.
        HTTP 401 Unauthorized if key is missing or invalid.
        HTTP 429 Too Many Requests if rate limit is exceeded.
    """
    key_to_check = x_judge_api_key or authorization

    if not key_to_check:
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return {"status": "DENIED", "detail": "Missing API Key or Authorization header"}

    record = auth_service.verify_key(key_to_check)
    if not record:
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return {"status": "DENIED", "detail": "Invalid or revoked API key"}

    # Rate limiting check
    key_id = record.get("key_id", "anon_key")
    role = record.get("role", "dev")
    allowed, current_count = auth_service.check_rate_limit(key_id, role)

    if not allowed:
        response.status_code = status.HTTP_429_TOO_MANY_REQUESTS
        return {
            "status": "RATE_LIMITED",
            "detail": f"Rate limit exceeded for role [{role}]. Maximum requests reached.",
            "current_req_count": current_count,
        }

    # Inject response headers for upstream forwarding by Envoy
    response.headers["X-User-ID"] = record.get("key_id", "unknown")
    response.headers["X-User-Role"] = role
    response.headers["X-User-Scopes"] = ",".join(record.get("scopes", []))
    response.headers["X-Envoy-Auth-Status"] = "APPROVED"

    return {
        "status": "APPROVED",
        "key_id": record.get("key_id"),
        "role": role,
        "scopes": record.get("scopes", []),
    }


@router.post("/realms/arm-platform/protocol/openid-connect/token")
async def keycloak_token_endpoint(
    request: Request,
    response: Response,
    grant_type: str = Form("client_credentials"),
    client_id: str | None = Form(None),
    client_secret: str | None = Form(None),
):
    """Keycloak M2M OAuth2 Token Endpoint returning JWT access tokens."""
    # Handle JSON payload fallback if form-data is not sent
    if not client_id or not client_secret:
        try:
            body = await request.json()
            grant_type = body.get("grant_type", grant_type)
            client_id = body.get("client_id", client_id)
            client_secret = body.get("client_secret", client_secret)
        except Exception:
            pass

    if grant_type != "client_credentials":
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {"error": "unsupported_grant_type", "error_description": "Only client_credentials grant type is supported."}

    valid_secret = client_secret in ["mcp_ci_runner_secret_2026", "arm_m2m_client_secret_stub_2026"]
    if client_id != "github-ci-runner" or not valid_secret:
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return {"error": "invalid_client", "error_description": "Invalid client_id or client_secret"}

    now = int(time.time())
    exp = now + 900  # 15 minutes lifespan

    header_dict = {"alg": "RS256", "typ": "JWT", "kid": "keycloak-m2m-key-1"}
    payload_dict = {
        "exp": exp,
        "iat": now,
        "iss": "https://keycloak.internal/realms/arm-platform",
        "sub": "service-account-github-ci-runner",
        "azp": "github-ci-runner",
        "client_id": "github-ci-runner",
        "grant_type": "client_credentials",
        "scope": "tools:register profile email",
        "realm_access": {"roles": ["mcp-registrar", "default-roles-arm-platform"]},
    }

    def b64_encode(data_dict: dict) -> str:
        raw = json.dumps(data_dict).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    header_b64 = b64_encode(header_dict)
    payload_b64 = b64_encode(payload_dict)
    signature_b64 = b64_encode({"sig": "mock_rs256_keycloak_signature"})

    access_token = f"{header_b64}.{payload_b64}.{signature_b64}"

    return {
        "access_token": access_token,
        "expires_in": 900,
        "refresh_expires_in": 0,
        "token_type": "Bearer",
        "not-before-policy": 0,
        "scope": "tools:register profile email",
    }


@router.get("/realms/arm-platform/protocol/openid-connect/certs")
async def keycloak_certs_endpoint():
    """Keycloak JWKS Public Key Certificates Endpoint."""
    return {
        "keys": [
          {
            "kid": "keycloak-m2m-key-1",
            "kty": "RSA",
            "alg": "RS256",
            "use": "sig",
            "n": "vLLM_Keycloak_Public_Modulus_Stub_2026",
            "e": "AQAB",
          }
        ]
    }
