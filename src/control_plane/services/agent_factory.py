"""Central Agent Factory Service configuring CodeMode and Prompt Cache Protection."""

import logging
from typing import Any

from src.control_plane.types import ArmPlatformDeps

logger = logging.getLogger("mvcp.agent_factory")

# Defensive imports with fallback support
try:
    from pydantic_ai import Agent
    from pydantic_ai_harness import CodeMode
    PYDANTIC_AI_HARNESS_AVAILABLE = True
except ImportError:
    try:
        from pydantic_ai import Agent
        from pydantic_ai_harness.capabilities.code_mode import CodeMode
        PYDANTIC_AI_HARNESS_AVAILABLE = True
    except ImportError:
        PYDANTIC_AI_HARNESS_AVAILABLE = False
        logger.warning(
            "pydantic-ai-harness not installed. Agent Factory will operate in simulation mode."
        )


class DummyCodeModeCapability:
    """Mock CodeMode capability fallback when harness package is unavailable."""

    def __init__(self, dynamic_catalog: bool = True, tools: dict[str, Any] | None = None):
        self.dynamic_catalog = dynamic_catalog
        self.tools = tools or {"code_mode": True}


def create_arm_agent(model_name: str = "anthropic:claude-3-5-sonnet") -> Any:
    """Constructs an Agent instance with CodeMode enabled and prompt cache protection.

    `dynamic_catalog=True` ensures new tool stubs injected during deferred discovery
    are passed via dynamic instructions / `ctx.enqueue` rather than mutating `run_code`'s
    schema, preserving provider KV prompt cache.

    Args:
        model_name: Target model identifier string.

    Returns:
        Configured Pydantic AI Agent instance (or simulation runner).
    """
    logger.info(f"Constructing Arm Agent with CodeMode (dynamic_catalog=True) for model [{model_name}]")

    if PYDANTIC_AI_HARNESS_AVAILABLE:
        code_mode = CodeMode(
            dynamic_catalog=True,
            tools={"code_mode": True}  # Metadata filter for tools tagged code_mode=True
        )
        return Agent(
            model=model_name,
            capabilities=[code_mode],
            deps_type=ArmPlatformDeps,
        )
    else:
        # Fallback simulation container
        code_mode = DummyCodeModeCapability(dynamic_catalog=True, tools={"code_mode": True})
        return {
            "model_name": model_name,
            "capabilities": [code_mode],
            "deps_type": ArmPlatformDeps,
            "status": "simulation_mode"
        }
