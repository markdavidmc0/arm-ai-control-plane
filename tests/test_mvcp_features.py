import json
import asyncio
from fastapi.testclient import TestClient

from src.control_plane.main import app, tasks_db

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
    """Verify that the MCP tools/list JSON-RPC schema exposes the optimize_kernel tool."""
    rpc_payload = {
        "jsonrpc": "2.0",
        "id": "req-1",
        "method": "tools/list",
        "params": {}
    }
    response = client.post("/api/v1/mcp", json=rpc_payload)
    assert response.status_code == 200
    
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == "req-1"
    
    result = data["result"]
    assert "tools" in result
    tools = result["tools"]
    assert len(tools) == 1
    
    tool = tools[0]
    assert tool["name"] == "optimize_kernel"
    assert "inputSchema" in tool
    assert "code" in tool["inputSchema"]["properties"]

def test_mcp_resources_list():
    """Verify that the MCP resources/list exposes the Heatmap payload URI."""
    rpc_payload = {
        "jsonrpc": "2.0",
        "id": "req-2",
        "method": "resources/list",
        "params": {}
    }
    response = client.post("/api/v1/mcp", json=rpc_payload)
    assert response.status_code == 200
    
    data = response.json()
    result = data["result"]
    assert "resources" in result
    resources = result["resources"]
    assert len(resources) == 1
    assert resources[0]["uri"] == "mvcp://heatmap/latest"

def test_mcp_resources_read():
    """Verify that the MCP resources/read returns color-coded visual Heatmap cells."""
    rpc_payload = {
        "jsonrpc": "2.0",
        "id": "req-3",
        "method": "resources/read",
        "params": {
            "uri": "mvcp://heatmap/latest"
        }
    }
    response = client.post("/api/v1/mcp", json=rpc_payload)
    assert response.status_code == 200
    
    data = response.json()
    result = data["result"]
    assert "contents" in result
    content = result["contents"][0]
    assert content["uri"] == "mvcp://heatmap/latest"
    
    # Assert JSON Heatmap body structures are mapped
    heatmap_body = json.loads(content["text"])
    assert "heatmap" in heatmap_body
    cells = heatmap_body["heatmap"]
    assert len(cells) == 45
    
    # Assert naive column-major loops map to unvectorized amber cells
    amber_lines = [cell for cell in cells if cell["color"] == "amber"]
    assert len(amber_lines) > 0
    assert any(cell["line"] == 17 for cell in amber_lines)

def test_mcp_invalid_method():
    """Verify that an invalid MCP JSON-RPC call returns error code -32601."""
    rpc_payload = {
        "jsonrpc": "2.0",
        "id": "req-4",
        "method": "non_existent_mcp_method",
        "params": {}
    }
    response = client.post("/api/v1/mcp", json=rpc_payload)
    assert response.status_code == 200
    
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == -32601

def test_naive_vs_optimized_kernel_evaluation():
    """Verify that the orchestrator accurately differentiates compiler metrics.

    Naive column-major loops should report missed vectorization, whereas loops 
    incorporating Arm KleidiAI/Neon vector primitives must register green, 
    active vector registers, and high SME2 execution metrics.
    """
    # 1. Test Naive Loop Behavior
    naive_code = "void naive_mul() { C[i * N + j] += A[i * K + k] * B[k * N + j]; }"
    response_naive = client.post("/api/v1/optimize", json={"code": naive_code})
    assert response_naive.status_code == 200
    task_id_naive = response_naive.json()["task_id"]
    
    # Wait for background task simulation
    tasks_db[task_id_naive]["status"] = "completed"
    from src.control_plane.orchestrator import SandboxOrchestrator
    
    # Manually run orchestrator simulation to verify logic
    orchestrator = SandboxOrchestrator()
    profile_naive = asyncio.run(orchestrator._run_simulated_optimization(task_id_naive, naive_code))
    
    assert profile_naive["sme2_utilization_pct"] == 0.0
    assert len(profile_naive["missed_vectorization_lines"]) > 0
    assert len(profile_naive["optimized_microkernel_lines"]) == 0
    assert "Naive Scalar Fallback" in profile_naive["runtime"]
    
    # 2. Test KleidiAI Optimized Loop Behavior
    optimized_code = "void kernel() { /* Arm KleidiAI Neon micro-kernel acceleration SME */ }"
    task_id_opt = "task-opt-123"
    profile_opt = asyncio.run(orchestrator._run_simulated_optimization(task_id_opt, optimized_code))
    
    assert profile_opt["sme2_utilization_pct"] == 82.4
    assert len(profile_opt["optimized_microkernel_lines"]) > 0
    assert len(profile_opt["missed_vectorization_lines"]) == 0
    assert "KleidiAI" in profile_opt["runtime"]
    assert profile_opt["assembly_insights"]["neon_instructions"] == 128
    assert profile_opt["assembly_insights"]["sme2_registers_active"] == 4

def test_streamable_mcp_gateway():
    """Verify that the Streamable HTTP gateway streams newline-delimited JSON-RPC frames."""
    rpc_payload = {
        "jsonrpc": "2.0",
        "id": "test-stream-id-123",
        "method": "tools/call",
        "params": {
            "name": "optimize_kernel",
            "arguments": {
                "code": "void kernel() { /* Streaming Test */ }"
            }
        }
    }
    
    # Since FastAPI StreamingResponse uses background chunking, we can mock-test 
    # its generator stream using TestClient's stream-based context manager
    with client.stream("POST", "/api/v1/mcp/stream", json=rpc_payload) as response:
        assert response.status_code == 200
        
        frames = []
        for line in response.iter_lines():
            if line:
                frames.append(json.loads(line))
                
        # Assert that we received exactly 4 frames sequentially over the single connection
        assert len(frames) == 4
        
        # Frame 1: Handshake and initial response
        assert frames[0]["jsonrpc"] == "2.0"
        assert frames[0]["id"] == "test-stream-id-123"
        assert "result" in frames[0]
        
        # Frame 2: Compiler sandbox spinning up
        assert frames[1]["method"] == "notifications/progress"
        assert frames[1]["params"]["status"] == "compiling"
        assert frames[1]["params"]["sandbox_health"] == "SANDBOX_GVISOR_ACTIVE"
        
        # Frame 3: Optimization processing
        assert frames[2]["method"] == "notifications/progress"
        assert frames[2]["params"]["status"] == "optimizing_assembly"
        assert frames[2]["params"]["sandbox_health"] == "KLEIDIAI_ACTIVE"
        
        # Frame 4: Successful profile outputs
        assert frames[3]["method"] == "resources/update"
        assert frames[3]["params"]["status"] == "completed"
        assert frames[3]["params"]["results"]["target_hardware"] == "Arm Cortex-X925"
