"""End-to-End Control Plane Tool Passthrough Integration Tests.

Asserts that tools/call requests received by MCPServer are forwarded directly
to SandboxOrchestrator / LocalToolDispatcher without intermediate payload mutation or hardcoding.
"""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.control_plane.main import app
from src.control_plane.mcp_server import MCPServer

client = TestClient(app)


@pytest.mark.asyncio
async def test_mcp_server_tools_call_passthrough_direct_dispatcher():
    """Verify MCPServer forwards tools/call arguments directly to LocalToolDispatcher."""
    mock_dispatcher = AsyncMock()
    mock_dispatcher.dispatch_tool_call.return_value = {
        "status": "SUCCESS",
        "output": {"passthrough_received": True, "custom_arg": "value_123"},
    }

    mock_orchestrator = AsyncMock()
    mock_orchestrator.k8s_client_configured = False

    server = MCPServer(orchestrator=mock_orchestrator, tool_dispatcher=mock_dispatcher)

    rpc_payload = {
        "jsonrpc": "2.0",
        "id": "passthrough-req-1",
        "method": "tools/call",
        "params": {
            "name": "custom_workspace_tool",
            "arguments": {"custom_arg": "value_123", "param_b": 42},
        },
    }

    response = await server.handle_mcp_request(rpc_payload)
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "passthrough-req-1"
    assert "result" in response

    mock_dispatcher.dispatch_tool_call.assert_awaited_once_with(
        "custom_workspace_tool", {"custom_arg": "value_123", "param_b": 42}
    )


@pytest.mark.asyncio
async def test_mcp_server_tools_call_passthrough_orchestrator():
    """Verify MCPServer forwards tools/call code directly to SandboxOrchestrator."""
    mock_orchestrator = AsyncMock()
    mock_orchestrator.k8s_client_configured = True
    mock_orchestrator.optimize_and_profile.return_value = {
        "task_id": "passthrough-task-888",
        "status": "success",
        "target_hardware": "Cortex-X925",
    }

    server = MCPServer(orchestrator=mock_orchestrator)

    rpc_payload = {
        "jsonrpc": "2.0",
        "id": "passthrough-req-2",
        "method": "tools/call",
        "params": {
            "name": "optimize_kernel",
            "arguments": {"code": "void passthrough_kernel() {}"},
        },
    }

    response = await server.handle_mcp_request(rpc_payload)
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "passthrough-req-2"
    assert "result" in response

    mock_orchestrator.optimize_and_profile.assert_awaited_once()
    call_args = mock_orchestrator.optimize_and_profile.call_args[0]
    assert call_args[1] == "void passthrough_kernel() {}"
