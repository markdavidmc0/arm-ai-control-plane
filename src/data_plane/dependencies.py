"""Data Plane FastAPI Dependency Injection Providers and App Lifespan Management.

Manages lifecycles for tool dispatchers and sandboxed REPL runners, exposing
explicit dependency providers for FastAPI routes.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from src.data_plane.context import get_current_user_context
from src.data_plane.schemas import DataPlaneUserContext
from src.data_plane.worker import (
    BaseToolDispatcher,
    DataPlaneSandboxRunner,
    LocalToolDispatcher,
)


@asynccontextmanager
async def data_plane_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """App lifespan context manager initializing stateful Data Plane execution workers."""
    app.state.sandbox_runner = DataPlaneSandboxRunner()
    app.state.dispatcher = LocalToolDispatcher(sandbox_runner=app.state.sandbox_runner)
    yield


def get_tool_dispatcher(request: Request) -> BaseToolDispatcher:
    """Dependency provider returning the configured BaseToolDispatcher instance."""
    if hasattr(request.app, "state") and hasattr(request.app.state, "dispatcher"):
        return request.app.state.dispatcher  # type: ignore[no-any-return]
    return LocalToolDispatcher()


def get_sandbox_runner(request: Request) -> DataPlaneSandboxRunner:
    """Dependency provider returning the configured DataPlaneSandboxRunner instance."""
    if hasattr(request.app, "state") and hasattr(request.app.state, "sandbox_runner"):
        return request.app.state.sandbox_runner  # type: ignore[no-any-return]
    return DataPlaneSandboxRunner()


def get_user_context() -> DataPlaneUserContext | None:
    """Dependency provider retrieving current task-isolated DataPlaneUserContext."""
    return get_current_user_context()


__all__ = [
    "data_plane_lifespan",
    "get_tool_dispatcher",
    "get_sandbox_runner",
    "get_user_context",
]
