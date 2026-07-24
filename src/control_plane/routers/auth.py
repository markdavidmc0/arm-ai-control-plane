"""Auth APIRouter.

Serves `/api/v1/internal/auth-check` for Envoy `ext_authz` sidecar validation.
Inspects incoming `X-Judge-API-Key` and `Authorization: Bearer <key>` headers,
verifies salted SHA-256 digests, enforces sliding-window rate limits, and injects user headers.
"""

from fastapi import APIRouter, Header, Response, status
from src.control_plane.services.auth_service import AuthService

router = APIRouter(prefix="/api/v1/internal", tags=["Zero-Trust Auth Guard"])
auth_service = AuthService()


@router.get("/auth-check")
async def envoy_ext_authz_check(
    response: Response,
    x_judge_api_key: str | None = Header(None, alias="x-judge-api-key"),
    authorization: str | None = Header(None, alias="authorization"),
):
    """Sidecar authentication check endpoint called exclusively by Envoy proxy.

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
