"""Centralized FastAPI Dependency Injection container."""

from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from src.control_plane.services.llm_router import (
    LiteLLMClient,
    LLMClientProtocol,
    LLMRouterService,
)


class UserContext(BaseModel):
    """User context container parsed from pre-authenticated Envoy HTTP headers."""

    user_id: str = Field(..., description="Unique user identifier from X-User-ID header")
    role: str = Field("user", description="User role from X-User-Role header")
    scopes: list[str] = Field(
        default_factory=list, description="User scope list from X-User-Scopes header"
    )


def get_llm_client() -> LLMClientProtocol:
    """Dependency provider for execution client (LiteLLM for production)."""
    return LiteLLMClient()


def get_llm_router_service(
    llm_client: LLMClientProtocol = Depends(get_llm_client),
) -> LLMRouterService:
    """Dependency provider for LLMRouterService."""
    return LLMRouterService(llm_client=llm_client)


# --- Route Guard / Security Dependencies ---


async def get_user_context(
    x_user_id: str | None = Header(None, alias="X-User-ID"),
    x_user_role: str | None = Header("user", alias="X-User-Role"),
    x_user_scopes: str | None = Header("", alias="X-User-Scopes"),
) -> UserContext:
    """Extracts pre-validated identity claims injected downstream by Envoy Edge Guard.

    Args:
        x_user_id: Injected user ID header.
        x_user_role: Injected user role header.
        x_user_scopes: Injected comma-separated user scopes header.

    Returns:
        UserContext instance containing identity claims.

    Raises:
        HTTPException: HTTP 401 Unauthorized if X-User-ID is missing or empty.
    """
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing upstream identity header (X-User-ID)",
        )

    scopes_str = x_user_scopes or ""
    scopes_list = [s.strip() for s in scopes_str.split(",") if s.strip()]

    return UserContext(
        user_id=x_user_id,
        role=x_user_role or "user",
        scopes=scopes_list,
    )
