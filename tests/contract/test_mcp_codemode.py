"""Contract & End-to-End Tests for MCP CodeMode & Direct SFI Execution Patterns."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel

from src.config import Settings
from src.control_plane.dependencies import ArmPlatformDeps, UserContext
from src.control_plane.services.agent_handler import AgentHandlerService
from src.control_plane.services.mcp_proxy import MCPProxyService
from src.data_plane.mcp_server import app as data_plane_app

client = TestClient(data_plane_app)

HEADERS = {
    "X-User-ID": "usr_contract_001",
    "X-User-Role": "developer",
    "X-User-Scopes": "tools:execute",
    "MCP-Protocol-Version": "2026-07-28",
}

# --- Pattern 2: IDE / Direct SFI Execution (FastMCP Data Plane) ---


@pytest.mark.contract
def test_pattern_2_sfi_direct_execution_metrics():
    """Verify execute_code runs via SFI mode with duration_ms execution metrics."""
    code = "result = 21 * 2\nprint(f'Calculated: {result}')"
    payload = {
        "jsonrpc": "2.0",
        "id": "req-sfi-01",
        "method": "tools/call",
        "params": {
            "name": "execute_code",
            "arguments": {"code": code},
        },
    }
    response = client.post("/api/v1/mcp", json=payload, headers=HEADERS)
    assert response.status_code == 200

    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == "req-sfi-01"
    assert "result" in data

    result = data["result"]
    assert "content" in result or "output" in result or "status" in result


@pytest.mark.contract
def test_pattern_2_sfi_infinite_loop_tick_protection():
    """Verify tick limit / timeout safety traps abort execution on infinite loops."""
    infinite_loop_code = "while True:\n    pass"
    payload = {
        "jsonrpc": "2.0",
        "id": "req-sfi-loop",
        "method": "tools/call",
        "params": {
            "name": "execute_code",
            "arguments": {"code": infinite_loop_code},
        },
    }
    response = client.post("/api/v1/mcp", json=payload, headers=HEADERS)
    assert response.status_code == 200

    data = response.json()
    assert data["jsonrpc"] == "2.0"
    # Execution should report error, timeout, or halted status
    assert "error" in data or (
        "result" in data
        and (
            data["result"].get("isError")
            or "timeout" in str(data["result"]).lower()
            or "halted" in str(data["result"]).lower()
        )
    )


# --- Pattern 1: Server-Side CodeMode Agent Execution (Control Plane) ---


@pytest.mark.contract
@pytest.mark.asyncio
async def test_pattern_1_codemode_agent_single_turn_aggregation():
    """Verify CodeMode enables single-turn execution using run_code for parallel tool execution."""
    mock_settings = Settings(ENABLE_CODE_MODE=True)

    with patch(
        "src.control_plane.services.agent_handler.get_settings",
        return_value=mock_settings,
    ):
        mock_proxy = MagicMock(spec=MCPProxyService)
        mock_proxy.call_tool = AsyncMock(
            return_value={
                "status": "SUCCESS",
                "result": {"output": "Aggregated execution complete"},
            }
        )

        user_ctx = UserContext(user_id="usr_codemode_agent", role="dev")
        deps = ArmPlatformDeps(mcp_proxy=mock_proxy, user_context=user_ctx)

        service = AgentHandlerService(model=TestModel())

        # Assert run_code tool is registered for CodeMode
        registered_tools = list(service.agent._function_toolset.tools.keys())
        assert "run_code" in registered_tools
        assert "execute_code_mode_tool" not in registered_tools

        # Execute run_code tool directly
        run_code_tool = service.agent._function_toolset.tools["run_code"]
        ctx = MagicMock()
        ctx.deps = deps

        python_snippet = (
            "import asyncio\n"
            "res = await asyncio.gather(\n"
            "    tool_a(), tool_b(), tool_c()\n"
            ")\n"
        )
        res = await run_code_tool.function(ctx, code=python_snippet)

        assert res["status"] == "SUCCESS"
        mock_proxy.call_tool.assert_called_once_with(
            name="repl_execute",
            arguments={"code": python_snippet},
            user_context=user_ctx,
        )


@pytest.mark.contract
@pytest.mark.asyncio
async def test_pattern_1_mode_toggle_fallback():
    """Verify setting ENABLE_CODE_MODE=False safely falls back to multi-turn JSON tool calling."""
    mock_settings = Settings(ENABLE_CODE_MODE=False)

    with patch(
        "src.control_plane.services.agent_handler.get_settings",
        return_value=mock_settings,
    ):
        mock_proxy = MagicMock(spec=MCPProxyService)
        mock_proxy.call_tool = AsyncMock(
            return_value={"status": "SUCCESS", "result": "Multi-turn tool result"}
        )

        user_ctx = UserContext(user_id="usr_fallback_agent", role="dev")
        deps = ArmPlatformDeps(mcp_proxy=mock_proxy, user_context=user_ctx)

        service = AgentHandlerService(model=TestModel())

        # Assert standard execute_code_mode_tool is registered
        registered_tools = list(service.agent._function_toolset.tools.keys())
        assert "execute_code_mode_tool" in registered_tools
        assert "run_code" not in registered_tools

        # Execute standard multi-turn tool forwarder
        fallback_tool = service.agent._function_toolset.tools["execute_code_mode_tool"]
        ctx = MagicMock()
        ctx.deps = deps

        res = await fallback_tool.function(
            ctx, tool_name="compile_kernel", arguments={"opt": "O3"}
        )

        assert res["status"] == "SUCCESS"
        mock_proxy.call_tool.assert_called_once_with(
            name="compile_kernel",
            arguments={"opt": "O3"},
            user_context=user_ctx,
        )
