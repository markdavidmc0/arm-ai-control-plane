"""Auth & Keycloak OIDC APIRouter.

Serves `/api/v1/internal/auth-check` for Envoy `ext_authz` sidecar validation,
and `/realms/arm-platform/protocol/openid-connect/token` for Keycloak M2M OAuth2 tokens.
"""

from typing import Any

from fastapi import APIRouter, Form, Header, Request, status
from fastapi.responses import JSONResponse

from src.control_plane.services.auth_service import AuthService

router = APIRouter(tags=["Zero-Trust Auth Guard & Keycloak OIDC"])
auth_service = AuthService()


@router.api_route("/api/v1/internal/auth-check", methods=["GET", "POST"])
@router.api_route("/api/v1/internal/auth-check/{full_path:path}", methods=["GET", "POST"])
async def envoy_ext_authz_check(
    request: Request,
    x_judge_api_key: str | None = Header(None, alias="x-judge-api-key"),
    authorization: str | None = Header(None, alias="authorization"),
):
    """Sidecar authentication check endpoint called by Envoy proxy.

    Returns:
        HTTP 200 OK with injected `X-User-Role` and `X-User-Scopes` on success.
        HTTP 401 Unauthorized with X-Envoy-Auth-Status: DENIED if key is missing or invalid.
        HTTP 429 Too Many Requests with X-Envoy-Auth-Status: DENIED if rate limit is exceeded.
    """
    key_to_check = x_judge_api_key or authorization

    # 1. Missing Credentials Path
    if not key_to_check:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"X-Envoy-Auth-Status": "DENIED"},
            content={"status": "DENIED", "detail": "Missing API Key or Authorization header"},
        )

    # 2. Invalid / Expired Credentials Path
    record = auth_service.verify_key(key_to_check)
    if not record:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"X-Envoy-Auth-Status": "DENIED"},
            content={"status": "DENIED", "detail": "Invalid or revoked API key"},
        )

    # 3. Rate Limiting Check Path
    key_id = record.get("key_id", "anon_key")
    role = record.get("role", "dev")
    allowed, current_count = auth_service.check_rate_limit(key_id, role)

    if not allowed:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={
                "X-Envoy-Auth-Status": "DENIED",
                "Retry-After": "60",
            },
            content={
                "status": "RATE_LIMITED",
                "detail": f"Rate limit exceeded for role [{role}]. Maximum requests reached.",
                "current_req_count": current_count,
            },
        )

    # 4. Approved Path (HTTP 200 OK)
    scopes_str = ",".join(record.get("scopes", []))
    headers = {
        "X-User-ID": str(record.get("key_id", "unknown")),
        "X-User-Role": role,
        "X-User-Scopes": scopes_str,
        "X-Envoy-Auth-Status": "APPROVED",
    }

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        headers=headers,
        content={
            "status": "APPROVED",
            "key_id": record.get("key_id"),
            "role": role,
            "scopes": record.get("scopes", []),
        },
    )


@router.post("/realms/arm-platform/protocol/openid-connect/token")
async def keycloak_token_endpoint(
    request: Request,
    grant_type: str = Form("client_credentials"),
    client_id: str | None = Form(None),
    client_secret: str | None = Form(None),
    subject_token: str | None = Form(None),
    subject_token_type: str | None = Form(None),
    subject_issuer: str | None = Form(None),
    client_assertion: str | None = Form(None),
    client_assertion_type: str | None = Form(None),
):
    """Keycloak M2M OAuth2 Token Endpoint returning JWT access tokens.

    Supports secretless GitHub Actions OIDC exchange, client JWT assertions, and secret verification.
    """
    # Fallback to JSON payload if request body is formatted as application/json
    try:
        body = await request.json()
        grant_type = body.get("grant_type", grant_type)
        client_id = body.get("client_id", client_id)
        client_secret = body.get("client_secret", client_secret)
        subject_token = body.get("subject_token", subject_token)
        client_assertion = body.get("client_assertion", client_assertion)
    except Exception:
        pass

    oidc_token = subject_token or client_assertion

    # Secretless OIDC Validation Path
    is_secretless_authenticated = False
    if oidc_token and oidc_token.count(".") == 2:
        verified_payload = auth_service.verify_jwt_token(oidc_token)
        if verified_payload:
            is_secretless_authenticated = True

    # Secret Verification Path delegated to AuthService
    is_secret_authenticated = auth_service.verify_client_credentials(client_id, client_secret)

    if not is_secretless_authenticated and not is_secret_authenticated:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "error": "invalid_client",
                "error_description": "Invalid OIDC Token, client_id, or client_secret",
            },
        )

    access_token = auth_service.mint_keycloak_jwt(
        grant_type=grant_type, client_id=client_id or "github-ci-runner"
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "access_token": access_token,
            "expires_in": 900,
            "refresh_expires_in": 0,
            "token_type": "Bearer",
            "not-before-policy": 0,
            "scope": "tools:register profile email",
        },
    )


@router.get("/realms/arm-platform/protocol/openid-connect/certs")
async def keycloak_certs_endpoint():
    """Keycloak JWKS Public Key Certificates Endpoint."""
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
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
        },
    )
