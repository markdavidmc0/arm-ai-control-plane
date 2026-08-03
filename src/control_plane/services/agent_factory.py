"""Central Agent Factory Service for Production CodeMode Agent Provisioning."""

import logging
from typing import Any

from pydantic_ai import Agent
from pydantic_ai_harness import CodeMode

from src.control_plane.types import ArmPlatformDeps

logger = logging.getLogger("mvcp.agent_factory")


def create_arm_agent(
    model_name: str | Any = "anthropic:claude-3-5-sonnet",
) -> Agent[ArmPlatformDeps, str]:
    """Constructs a production Pydantic AI Agent instance with CodeMode enabled.

    `dynamic_catalog=True` ensures new tool stubs injected during deferred discovery
    are passed via dynamic instructions / `ctx.enqueue` rather than mutating `run_code`'s
    schema, preserving provider KV prompt cache.

    Args:
        model_name: Target model identifier string or Pydantic AI Model object.

    Returns:
        Configured Pydantic AI Agent instance.
    """
    logger.info(f"Constructing production Arm Agent with CodeMode for model [{model_name}]")

    code_mode = CodeMode(
        dynamic_catalog=True,
        tools={"code_mode": True},  # Metadata filter for tools tagged code_mode=True
    )

    return Agent(
        model=model_name,
        capabilities=[code_mode],
        deps_type=ArmPlatformDeps,
    )
