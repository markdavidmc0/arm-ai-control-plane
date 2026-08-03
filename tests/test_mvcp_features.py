import asyncio
import json

from fastapi.testclient import TestClient

from src.control_plane.main import app

client = TestClient(app)


def test_health_endpoint():
    """Verify that the gateway health and WireGuard identity layer are reported correctly."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "gke_orchestrator_connected" in data
    assert data["identity_layer"] == "tailscale_tsnet"


def test_mcp_tools_list_schema():
    """Verify that the MCP tools/list JSON-RPC schema dynamically exposes catalog tools."""
    rpc_payload = {"jsonrpc": "2.0", "id": "req-1", "method": "tools/list", "params": {}}
    response = client.post("/api/v1/mcp", json=rpc_payload)
    assert response.status_code == 200

    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == "req-1"

    result = data["result"]
    assert "tools" in result
    tools = result["tools"]
    assert len(tools) >= 1

    tool_names = [t["name"] for t in tools]
    assert "optimize_kernel" in tool_names


def test_mcp_resources_list():
    """Verify that the MCP resources/list exposes resources schema."""
    rpc_payload = {"jsonrpc": "2.0", "id": "req-2", "method": "resources/list", "params": {}}
    response = client.post("/api/v1/mcp", json=rpc_payload)
    assert response.status_code == 200

    data = response.json()
    result = data["result"]
    assert "resources" in result
    assert isinstance(result["resources"], list)


def test_mcp_invalid_method():
    """Verify that an invalid MCP JSON-RPC call returns error code -32601."""
    rpc_payload = {
        "jsonrpc": "2.0",
        "id": "req-4",
        "method": "non_existent_mcp_method",
        "params": {},
    }
    response = client.post("/api/v1/mcp", json=rpc_payload)
    assert response.status_code == 200

    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == -32601


def test_naive_vs_optimized_kernel_evaluation():
    """Verify that the tool dispatcher accurately differentiates compiler evaluation requests."""
    from src.data_plane.worker.tool_dispatcher import LocalToolDispatcher

    dispatcher = LocalToolDispatcher()
    naive_code = "void naive_mul() { C[i * N + j] += A[i * K + k] * B[k * N + j]; }"
    profile_naive = asyncio.run(
        dispatcher.dispatch_tool_call("profile_and_optimize_kernel", {"source_code": naive_code})
    )

    assert profile_naive["jsonrpc"] == "2.0"
    assert profile_naive["result"]["status"] == "SUCCESS"
    assert "content" in profile_naive["result"]


def test_streamable_mcp_gateway():
    """Verify that the Streamable HTTP gateway streams newline-delimited JSON-RPC frames."""
    rpc_payload = {
        "jsonrpc": "2.0",
        "id": "test-stream-id-123",
        "method": "tools/call",
        "params": {
            "name": "optimize_kernel",
            "arguments": {"code": "void kernel() { /* Streaming Test */ }"},
        },
    }

    with client.stream("POST", "/api/v1/mcp/stream", json=rpc_payload) as response:
        assert response.status_code == 200

        frames = []
        for line in response.iter_lines():
            if line:
                frames.append(json.loads(line))

        assert len(frames) == 1
        assert frames[0]["jsonrpc"] == "2.0"
        assert frames[0]["id"] == "test-stream-id-123"
        assert "result" in frames[0]


def test_orchestrator_parse_profile_security_metadata():
    """Verify _parse_profile_from_logs accurately reports native-runc-arm vs gvisor (runsc-arm)."""
    from src.control_plane.orchestrator import SandboxOrchestrator

    orchestrator = SandboxOrchestrator()
    logs = '===TSNET_STREAM_START===\n{"status": "success"}\n===TSNET_STREAM_END==='

    profile_gvisor = orchestrator._parse_profile_from_logs(logs, "task-1", use_gvisor=True)
    assert profile_gvisor["sandbox_security"] == "gvisor (runsc-arm)"

    orchestrator.allow_native_benchmarks = True
    profile_native = orchestrator._parse_profile_from_logs(logs, "task-2", use_gvisor=False)
    assert profile_native["sandbox_security"] == "native-runc-arm"
