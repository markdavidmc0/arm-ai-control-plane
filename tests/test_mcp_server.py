from unittest.mock import AsyncMock

import pytest

from src.control_plane.mcp_server import MCPServer


@pytest.mark.asyncio
async def test_mcp_server_initialize():
    """Verify handle_mcp_request handles standard initialize and initialized RPC calls."""
    server = MCPServer()

    init_req = {"jsonrpc": "2.0", "id": "init-1", "method": "initialize", "params": {}}
    init_res = await server.handle_mcp_request(init_req)
    assert init_res["jsonrpc"] == "2.0"
    assert init_res["id"] == "init-1"
    assert init_res["result"]["serverInfo"]["name"] == "mvcp-gke-gateway"

    ack_req = {"jsonrpc": "2.0", "id": "ack-1", "method": "notifications/initialized", "params": {}}
    ack_res = await server.handle_mcp_request(ack_req)
    assert ack_res["jsonrpc"] == "2.0"
    assert ack_res["id"] == "ack-1"


@pytest.mark.asyncio
async def test_mcp_server_dynamic_tools_list():
    """Verify tools/list fetches tools dynamically from the Data Plane catalog."""
    mock_dispatcher = AsyncMock()
    mock_dispatcher._read_catalog.return_value = [
        {
            "name": "dynamic_compiler_tool",
            "description": "Dynamic C++ compiler tool",
            "inputSchema": {"type": "object", "properties": {"code": {"type": "string"}}},
        }
    ]

    server = MCPServer(tool_dispatcher=mock_dispatcher)
    req = {"jsonrpc": "2.0", "id": "req-tools-list", "method": "tools/list", "params": {}}

    res = await server.handle_mcp_request(req)
    assert res["jsonrpc"] == "2.0"
    assert "result" in res
    tools = res["result"]["tools"]
    assert len(tools) == 1
    assert tools[0]["name"] == "dynamic_compiler_tool"


@pytest.mark.asyncio
async def test_mcp_server_handle_request_tools_call_async_mock():
    """Verify handle_mcp_request awaits orchestrator.optimize_and_profile and returns json payload."""
    mock_orchestrator = AsyncMock()
    mock_orchestrator.k8s_client_configured = True
    mock_orchestrator.optimize_and_profile.return_value = {
        "task_id": "test-mock-task-123",
        "status": "success",
        "sme2_utilization_pct": 98.2,
        "latency_ttft_impact": "85% TTFT Latency Reduction",
        "peak_ram_mb": 210,
    }

    server = MCPServer(orchestrator=mock_orchestrator)
    req = {
        "jsonrpc": "2.0",
        "id": "req-100",
        "method": "tools/call",
        "params": {"name": "optimize_kernel", "arguments": {"code": "void mock_kernel() {}"}},
    }

    response = await server.handle_mcp_request(req)
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "req-100"
    assert "result" in response
    content_text = response["result"]["content"][0]["text"]
    assert "test-mock-task-123" in content_text
    mock_orchestrator.optimize_and_profile.assert_awaited_once()


@pytest.mark.asyncio
async def test_mcp_server_dispatcher_fallback_call():
    """Verify tools/call delegates to LocalToolDispatcher when k8s client is not configured."""
    mock_orchestrator = AsyncMock()
    mock_orchestrator.k8s_client_configured = False

    mock_dispatcher = AsyncMock()
    mock_dispatcher.dispatch_tool_call.return_value = {
        "status": "SUCCESS",
        "output": "Dispatched via LocalToolDispatcher",
    }

    server = MCPServer(orchestrator=mock_orchestrator, tool_dispatcher=mock_dispatcher)
    req = {
        "jsonrpc": "2.0",
        "id": "req-101",
        "method": "tools/call",
        "params": {"name": "ros2_pointcloud_voxelizer_profile", "arguments": {"voxel_size": 0.05}},
    }

    response = await server.handle_mcp_request(req)
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "req-101"
    assert "result" in response
    mock_dispatcher.dispatch_tool_call.assert_awaited_once_with(
        "ros2_pointcloud_voxelizer_profile", {"voxel_size": 0.05}
    )


@pytest.mark.asyncio
async def test_mcp_server_runtime_error_json_rpc_structure():
    """Verify handle_mcp_request returns JSON-RPC error when orchestrator raises RuntimeError."""
    mock_orchestrator = AsyncMock()
    mock_orchestrator.k8s_client_configured = True
    mock_orchestrator.optimize_and_profile.side_effect = RuntimeError(
        "GKE Sandbox Pod execution failed"
    )

    server = MCPServer(orchestrator=mock_orchestrator)
    req = {
        "jsonrpc": "2.0",
        "id": "req-102",
        "method": "tools/call",
        "params": {
            "name": "optimize_kernel",
            "arguments": {"code": "invalid_code"},
        },
    }

    response = await server.handle_mcp_request(req)
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "req-102"
    assert "error" in response
    assert response["error"]["code"] == -32603
    assert "GKE Sandbox Pod execution failed" in response["error"]["message"]


@pytest.mark.asyncio
async def test_mcp_server_timeout_error_json_rpc_structure():
    """Verify handle_mcp_request returns JSON-RPC error when orchestrator raises TimeoutError."""
    mock_orchestrator = AsyncMock()
    mock_orchestrator.k8s_client_configured = True
    mock_orchestrator.optimize_and_profile.side_effect = TimeoutError(
        "Sandbox execution timed out after 180 seconds."
    )

    server = MCPServer(orchestrator=mock_orchestrator)
    req = {
        "jsonrpc": "2.0",
        "id": "req-103",
        "method": "tools/call",
        "params": {
            "name": "optimize_kernel",
            "arguments": {"code": "long_running_code"},
        },
    }

    response = await server.handle_mcp_request(req)
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "req-103"
    assert "error" in response
    assert response["error"]["code"] == -32603
    assert "timed out" in response["error"]["message"]
