"""Centralized FastAPI Dependency Injection container."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx
from fastapi import Depends, Header, HTTPException, status

from src.control_plane.config import Settings, get_settings
from src.control_plane.schemas import UserContext
from src.control_plane.services.llm_router import (
    LiteLLMClient,
    LLMClientProtocol,
    LLMRouterService,
)

if TYPE_CHECKING:
    from src.control_plane.services.agent_handler import AgentHandlerService
    from src.control_plane.services.mcp_proxy import MCPProxyService


@dataclass
class ArmPlatformDeps:
    """Dependency injection container passed to Pydantic AI agent runs.

    Holds references to active UserContext, MCPProxyService, and session metadata.
    """

    mcp_proxy: MCPProxyService
    user_context: UserContext
    session_id: str = "default-session"
    workspace_context: str = "cloud-ai"


def get_llm_client() -> LLMClientProtocol:
    """Dependency provider for execution client (LiteLLM for production)."""
    return LiteLLMClient()


def get_llm_router_service(
    llm_client: LLMClientProtocol = Depends(get_llm_client),
) -> LLMRouterService:
    """Dependency provider for LLMRouterService."""
    return LLMRouterService(llm_client=llm_client)


async def get_mcp_proxy(
    settings: Settings = Depends(get_settings),
) -> AsyncGenerator[MCPProxyService, None]:
    """Dependency provider for MCPProxyService configuring client base_url."""
    from src.control_plane.services.mcp_proxy import MCPProxyService

    async with httpx.AsyncClient(
        base_url=settings.DATA_PLANE_URL,
        http2=True,
        timeout=30.0,
    ) as client:
        yield MCPProxyService(client=client)


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


def get_arm_deps(
    user_context: UserContext = Depends(get_user_context),
    mcp_proxy: MCPProxyService = Depends(get_mcp_proxy),
    session_id: str = Header("default-session", alias="X-Session-ID"),
    workspace_context: str = Header("cloud-ai", alias="X-Workspace-Context"),
) -> ArmPlatformDeps:
    """Dependency provider combining UserContext, MCPProxyService, and request metadata."""
    return ArmPlatformDeps(
        mcp_proxy=mcp_proxy,
        user_context=user_context,
        session_id=session_id,
        workspace_context=workspace_context,
    )


def get_agent_handler_service(
    model: str = "openai:gpt-4o",
) -> AgentHandlerService:
    """Dependency provider for AgentHandlerService."""
    from src.control_plane.services.agent_handler import AgentHandlerService

    return AgentHandlerService(model=model)
