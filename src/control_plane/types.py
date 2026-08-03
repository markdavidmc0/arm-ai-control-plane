"""Control plane type definitions and dependency injection dataclasses."""

from dataclasses import dataclass
from typing import Any


@dataclass
class ArmPlatformDeps:
    """Dependency injection container passed to Pydantic AI agent runs.

    Holds active session tokens, user/workspace metadata, and references
    to orchestrator & multiplexer services.
    """

    session_id: str
    workspace_context: str = "cloud-ai"
    user_id: str = "default-user"
    mcp_multiplexer: Any = None
    orchestrator: Any = None
