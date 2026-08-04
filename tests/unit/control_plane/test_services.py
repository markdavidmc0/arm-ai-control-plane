"""Unit & Integration Test Suite for Control Plane Services & SandboxOrchestrator.

Verifies MCPServer JSON-RPC request handling, MCPMultiplexerService dynamic tool discovery,
and SandboxOrchestrator pod manifest generation in isolation.
"""

from unittest.mock import AsyncMock

import pytest

from src.control_plane.orchestrator import SandboxOrchestrator
from src.control_plane.services.mcp_server import MCPServer

# ==============================================================================
# 1. MCPServer JSON-RPC Protocol Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_mcp_server_initialize():
    """Verify MCPServer handles 'initialize' method and returns serverInfo."""
    server = MCPServer()
    rpc_payload = {
        "jsonrpc": "2.0",
        "id": "init-req-1",
        "method": "initialize",
        "params": {},
    }

    response = await server.handle_mcp_request(rpc_payload)
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "init-req-1"
    assert response["result"]["serverInfo"]["name"] == "mvcp-gke-gateway"
    assert "capabilities" in response["result"]


@pytest.mark.asyncio
async def test_mcp_server_dynamic_tools_list():
    """Verify MCPServer handles 'tools/list' and dynamically fetches catalog tools."""
    server = MCPServer()
    rpc_payload = {
        "jsonrpc": "2.0",
        "id": "tools-req-1",
        "method": "tools/list",
        "params": {},
    }

    response = await server.handle_mcp_request(rpc_payload)
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "tools-req-1"
    assert "tools" in response["result"]
    assert len(response["result"]["tools"]) > 0


@pytest.mark.asyncio
async def test_mcp_server_handle_request_tools_call_async_mock():
    """Verify handle_mcp_request awaits orchestrator.optimize_and_profile and returns json payload."""
    mock_orchestrator = AsyncMock()
    mock_orchestrator.k8s_client_configured = True
    mock_orchestrator.optimize_and_profile.return_value = {
        "status": "success",
        "task_id": "test-task-123",
        "sme2_utilization": "82%",
    }

    server = MCPServer(orchestrator=mock_orchestrator)
    rpc_payload = {
        "jsonrpc": "2.0",
        "id": "call-req-1",
        "method": "tools/call",
        "params": {
            "name": "optimize_kernel",
            "arguments": {"code": "void matmul() {}"},
        },
    }

    response = await server.handle_mcp_request(rpc_payload)
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "call-req-1"
    assert "result" in response
    assert "content" in response["result"]
    mock_orchestrator.optimize_and_profile.assert_awaited_once()


@pytest.mark.asyncio
async def test_mcp_server_dispatcher_fallback_call():
    """Verify handle_mcp_request delegates tool execution when orchestrator is not k8s configured."""
    mock_orchestrator = AsyncMock()
    mock_orchestrator.k8s_client_configured = False

    mock_dispatcher = AsyncMock()
    mock_dispatcher.dispatch_tool_call.return_value = {
        "status": "SUCCESS",
        "output": "Simulated output",
    }

    server = MCPServer(orchestrator=mock_orchestrator, tool_dispatcher=mock_dispatcher)
    rpc_payload = {
        "jsonrpc": "2.0",
        "id": "call-req-2",
        "method": "tools/call",
        "params": {
            "name": "ros2_pointcloud_voxelizer_profile",
            "arguments": {"voxel_size": 0.05},
        },
    }

    response = await server.handle_mcp_request(rpc_payload)
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "call-req-2"
    assert "result" in response
    mock_dispatcher.dispatch_tool_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_mcp_server_runtime_error_json_rpc_structure():
    """Verify runtime exception inside orchestrator produces standard JSON-RPC -32603 error frame."""
    mock_orchestrator = AsyncMock()
    mock_orchestrator.k8s_client_configured = True
    mock_orchestrator.optimize_and_profile.side_effect = RuntimeError(
        "GKE Node pool capacity exhausted"
    )

    server = MCPServer(orchestrator=mock_orchestrator)
    rpc_payload = {
        "jsonrpc": "2.0",
        "id": "err-req-1",
        "method": "tools/call",
        "params": {
            "name": "optimize_kernel",
            "arguments": {"code": "invalid code"},
        },
    }

    response = await server.handle_mcp_request(rpc_payload)
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "err-req-1"
    assert "error" in response
    assert response["error"]["code"] == -32603
    assert "GKE Node pool capacity exhausted" in response["error"]["message"]


@pytest.mark.asyncio
async def test_mcp_server_timeout_error_json_rpc_structure():
    """Verify TimeoutError produces JSON-RPC -32603 error frame."""
    mock_orchestrator = AsyncMock()
    mock_orchestrator.k8s_client_configured = True
    mock_orchestrator.optimize_and_profile.side_effect = TimeoutError("Sandbox execution timed out")

    server = MCPServer(orchestrator=mock_orchestrator)
    rpc_payload = {
        "jsonrpc": "2.0",
        "id": "err-req-2",
        "method": "tools/call",
        "params": {
            "name": "optimize_kernel",
            "arguments": {"code": "void sleep_loop() {}"},
        },
    }

    response = await server.handle_mcp_request(rpc_payload)
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "err-req-2"
    assert "error" in response
    assert response["error"]["code"] == -32603
    assert "timed out" in response["error"]["message"]


# ==============================================================================
# 2. Control Plane Passthrough Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_mcp_server_tools_call_passthrough_direct_dispatcher(
    mock_dispatcher, mock_orchestrator
):
    """Verify MCPServer forwards tools/call arguments directly to LocalToolDispatcher."""
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


# ==============================================================================
# 3. SandboxOrchestrator Pod Manifest Tests
# ==============================================================================


def test_orchestrator_init_container_pod_manifest_structure():
    """Verify SandboxOrchestrator constructs pod manifests with initContainers and volume mounts."""
    orchestrator = SandboxOrchestrator()
    manifest = orchestrator.build_pod_manifest(
        task_id="test-task-1",
        cxx_code="void kernel() {}",
        use_gvisor=True,
        execution_mode="codemode",
    )

    assert manifest["apiVersion"] == "v1"
    assert manifest["kind"] == "Pod"
    assert manifest["metadata"]["name"] == "mvcp-sandbox-test-task-1"

    spec = manifest["spec"]
    assert spec["runtimeClassName"] == "gvisor"
    assert len(spec["initContainers"]) == 1
    assert spec["initContainers"][0]["name"] == "tools-installer"
    assert len(spec["volumes"]) == 1
    assert spec["volumes"][0]["name"] == "tools-volume"


def test_orchestrator_execution_mode_direct_omits_init_containers():
    """Verify build_pod_manifest omits initContainers and volumeMounts when execution_mode='direct'."""
    orchestrator = SandboxOrchestrator()
    manifest_direct = orchestrator.build_pod_manifest(
        task_id="test-task-2",
        cxx_code="void kernel() {}",
        use_gvisor=True,
        execution_mode="direct",
    )

    spec = manifest_direct["spec"]
    assert len(spec["initContainers"]) == 0
    assert len(spec["volumes"]) == 0


def test_orchestrator_bootstrap_command_generation():
    """Verify bootstrap Python snippet script generation."""
    orchestrator = SandboxOrchestrator()
    cmd = orchestrator._generate_sandbox_bootstrap_command("void matmul() {}")
    assert "import base64" in cmd
    assert "===TSNET_STREAM_START===" in cmd
