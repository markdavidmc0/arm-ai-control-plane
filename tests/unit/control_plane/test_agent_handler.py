"""Unit tests for Control Plane AgentHandlerService and ArmPlatformDeps."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from src.control_plane.dependencies import (
    ArmPlatformDeps,
    UserContext,
    get_agent_handler_service,
    get_arm_deps,
)
from src.control_plane.services.agent_handler import AgentHandlerService
from src.control_plane.services.mcp_proxy import MCPProxyService


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agent_handler_execute_tool_routing():
    """Verify execute_tool routes directly through MCPProxyService with active user_context."""
    mock_proxy = MagicMock(spec=MCPProxyService)
    mock_proxy.call_tool = AsyncMock(
        return_value={"jsonrpc": "2.0", "result": {"output": "SUCCESS"}}
    )

    user_ctx = UserContext(
        user_id="usr_agent_001",
        role="dev",
        scopes=["compiler"],
    )

    deps = ArmPlatformDeps(mcp_proxy=mock_proxy, user_context=user_ctx)
    service = AgentHandlerService(model=TestModel())

    result = await service.execute_tool(
        tool_name="compile_kernel",
        arguments={"source": "void fn() {}"},
        deps=deps,
    )

    assert result["jsonrpc"] == "2.0"
    assert result["result"]["output"] == "SUCCESS"

    mock_proxy.call_tool.assert_called_once_with(
        name="compile_kernel",
        arguments={"source": "void fn() {}"},
        user_context=user_ctx,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agent_handler_run_agent_tool_invocation():
    """Verify pydantic-ai agent correctly binds and executes tools via MCPProxyService."""
    mock_proxy = MagicMock(spec=MCPProxyService)
    mock_proxy.call_tool = AsyncMock(
        return_value={"status": "EXECUTED_IN_DATA_PLANE", "result": 42}
    )

    user_ctx = UserContext(user_id="usr_agent_002", role="admin", scopes=["all"])
    deps = ArmPlatformDeps(mcp_proxy=mock_proxy, user_context=user_ctx)

    # Use TestModel from pydantic-ai for deterministic offline testing
    test_model = TestModel()
    service = AgentHandlerService(model=test_model)

    res = await service.run_agent("Test agent prompt", deps=deps)

    assert res is not None
    assert res.output is not None
    mock_proxy.call_tool.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agent_handler_custom_agent_injection():
    """Verify AgentHandlerService accepts pre-configured custom Agent instance via constructor."""
    mock_agent = MagicMock(spec=Agent)
    mock_agent.run = AsyncMock(return_value="Mocked Agent Run Output")

    service = AgentHandlerService(agent=mock_agent)

    mock_proxy = MagicMock(spec=MCPProxyService)
    user_ctx = UserContext(user_id="usr_003", role="user")
    deps = ArmPlatformDeps(mcp_proxy=mock_proxy, user_context=user_ctx)

    res = await service.run_agent("Custom prompt", deps=deps)

    assert res == "Mocked Agent Run Output"
    mock_agent.run.assert_called_once_with("Custom prompt", deps=deps)


@pytest.mark.unit
def test_get_arm_deps_factory():
    """Verify get_arm_deps combines UserContext, MCPProxyService, and request metadata."""
    mock_proxy = MagicMock(spec=MCPProxyService)
    user_ctx = UserContext(user_id="usr_004", role="dev")

    deps = get_arm_deps(
        user_context=user_ctx,
        mcp_proxy=mock_proxy,
        session_id="sess-999",
        workspace_context="physical-ai",
    )

    assert deps.user_context == user_ctx
    assert deps.mcp_proxy == mock_proxy
    assert deps.session_id == "sess-999"
    assert deps.workspace_context == "physical-ai"


@pytest.mark.unit
def test_get_agent_handler_service_factory():
    """Verify get_agent_handler_service factory constructs AgentHandlerService instance."""
    service = get_agent_handler_service(model="test")
    assert isinstance(service, AgentHandlerService)
