"""Control Plane Agent Handler Service & Pydantic AI Orchestration."""

from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.models import KnownModelName, Model

from src.control_plane.dependencies import ArmPlatformDeps


class AgentHandlerService:
    """Orchestrates Pydantic AI Agent workflows forwarding tool calls to the Data Plane."""

    def __init__(
        self,
        model: Model | KnownModelName | str = "openai:gpt-4o",
        agent: Agent[ArmPlatformDeps, Any] | None = None,
    ) -> None:
        """Initializes AgentHandlerService with target model or pre-configured Agent.

        Args:
            model: Pydantic AI Model or model name string for agent runs.
            agent: Optional pre-constructed Agent instance for testing and dependency injection.
        """
        self.model = model
        if agent is not None:
            self.agent = agent
        else:
            self.agent = Agent(
                model=self.model,
                deps_type=ArmPlatformDeps,
                system_prompt=(
                    "You are an AI assistant orchestrating Arm federated workloads. "
                    "All tool executions must be forwarded through the Data Plane MCP Proxy."
                ),
            )

            @self.agent.tool
            async def execute_code_mode_tool(
                ctx: RunContext[ArmPlatformDeps],
                tool_name: str,
                arguments: dict[str, Any],
            ) -> dict[str, Any]:
                """Executes FastMCP tools on Data Plane via MCPProxyService forwarding.

                Args:
                    ctx: Agent run context containing ArmPlatformDeps.
                    tool_name: Name of the FastMCP tool to invoke.
                    arguments: Parameter mapping for the target tool.

                Returns:
                    Tool execution output response from the Data Plane.
                """
                return await ctx.deps.mcp_proxy.call_tool(
                    name=tool_name,
                    arguments=arguments,
                    user_context=ctx.deps.user_context,
                )

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        deps: ArmPlatformDeps,
    ) -> dict[str, Any]:
        """Directly forwards a tool execution request through the MCP Proxy using active deps.

        Args:
            tool_name: Name of the FastMCP tool to invoke.
            arguments: Parameter mapping for the tool.
            deps: ArmPlatformDeps containing active UserContext and MCPProxyService.

        Returns:
            JSON-RPC response dictionary from the Data Plane MCP proxy.
        """
        return await deps.mcp_proxy.call_tool(
            name=tool_name,
            arguments=arguments,
            user_context=deps.user_context,
        )

    async def run_agent(
        self,
        prompt: str,
        deps: ArmPlatformDeps,
    ) -> Any:
        """Executes an agent run using the provided prompt and platform dependencies.

        Args:
            prompt: User prompt for the agent execution run.
            deps: ArmPlatformDeps containing active UserContext and MCPProxyService.

        Returns:
            Agent run result object from pydantic-ai.
        """
        return await self.agent.run(prompt, deps=deps)
