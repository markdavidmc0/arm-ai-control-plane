"""Centralized FastAPI Dependency Injection container."""

from typing import Any

from fastapi import Depends, Header, HTTPException, status

from src.control_plane.services.auth_service import AuthService
from src.control_plane.services.llm_router import (
    LLMClientProtocol,
    LLMRouterService,
    LiteLLMClient,
)

# --- Service Providers ---

def get_auth_service() -> AuthService:
    """Dependency provider for AuthService."""
    return AuthService()


def get_llm_client() -> LLMClientProtocol:
    """Dependency provider for execution client (LiteLLM for production)."""
    return LiteLLMClient()


def get_llm_router_service(
    llm_client: LLMClientProtocol = Depends(get_llm_client),
) -> LLMRouterService:
    """Dependency provider for LLMRouterService."""
    return LLMRouterService(llm_client=llm_client)


# --- Route Guard / Security Dependencies ---

async def verify_authentication(
    authorization: str | None = Header(default=None),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, Any]:
    """FastAPI dependency enforcing API Key authentication on proxy endpoints."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )

    raw_key = authorization.removeprefix("Bearer ").strip()

    # Dynamic await support for sync or async AuthService methods
    auth_result = (
        auth_service.authenticate_key(raw_key)
        if hasattr(auth_service, "authenticate_key")
        else auth_service.verify_key(raw_key)
    )
    key_info = await auth_result if hasattr(auth_result, "__await__") else auth_result

    if not key_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key",
        )

    return key_info
