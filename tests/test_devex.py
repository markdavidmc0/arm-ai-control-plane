"""Unit Test Suite for Developer Experience & Context Reduction.

Verifies Workspace Slicing (< 1,500 tokens), mcp__search_tools meta-tool,
Code Mode gVisor sandbox execution, LLM Proxy headers, and Upstream MCP Server handshakes/proxying.
"""

from fastapi.testclient import TestClient
from src.control_plane.main import app

client = TestClient(app)


def test_workspace_slicing_token_limit():
    """Verify X-Workspace-Context: physical-ai returns < 1,500 tokens worth of tool schemas."""
    response = client.get("/api/v1/registry/tools", headers={"X-Workspace-Context": "physical-ai"})
    assert response.status_code == 200
    data = response.json()
    assert data["workspace_context"] == "physical-ai"
    assert data["estimated_token_footprint"] < 1500
    assert data["tool_count"] >= 3


def test_on_demand_search_meta_tool():
    """Verify mcp__search_tools('pointcloud') returns matching target tool schema dynamically."""
    response = client.post(
        "/api/v1/registry/search", json={"query": "pointcloud", "domain": "physical-ai"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["match_count"] >= 1
    assert "voxelizer" in data["matches"][0]["name"]


def test_gvisor_code_mode_execution():
    """Test script submission to /api/v1/sandbox/execute returning clean stdout output."""
    sample_script = "from arm_platform import profile_mca; print(profile_mca('void matmul(){}'))"
    response = client.post(
        "/api/v1/sandbox/execute", json={"script": sample_script, "timeout_seconds": 10}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert "cortex-x925" in data["stdout"] or "Execution completed" in data["stdout"]


def test_llm_proxy_headers():
    """Verify /v1/chat/completions injects X-LLM-Cost-USD and X-LLM-Prompt-Tokens headers."""
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "claude-3-5-sonnet",
            "messages": [{"role": "user", "content": "Optimize SVE matrix multiplication kernel."}],
        },
    )
    assert response.status_code == 200
    assert "X-LLM-Cost-USD" in response.headers
    assert "X-LLM-Prompt-Tokens" in response.headers
    assert "X-LLM-Latency-MS" in response.headers


def test_upstream_mcp_server_registration_and_search():
    """Test registering an official/upstream MCP server, verifying handshake tool integration, search, and call proxying."""
    # 1. Register upstream server
    reg_response = client.post(
        "/api/v1/registry/servers/register",
        json={
            "server_id": "official-arm-mcp-cluster",
            "domain": "base",
            "endpoint_url": "http://official-arm-mcp.internal:8000/mcp",
        },
    )
    assert reg_response.status_code == 200
    reg_data = reg_response.json()
    assert reg_data["status"] == "registered"
    assert reg_data["tool_count"] >= 2

    # 2. Verify upstream tools appear in Workspace Slicing
    tools_response = client.get(
        "/api/v1/registry/tools", headers={"X-Workspace-Context": "physical-ai"}
    )
    assert tools_response.status_code == 200
    tool_names = [t["name"] for t in tools_response.json()["tools"]]
    assert "arm_official_hardware_telemetry" in tool_names

    # 3. Verify mcp__search_tools finds upstream tools on-demand
    search_response = client.post(
        "/api/v1/registry/search", json={"query": "kleidiai", "domain": "base"}
    )
    assert search_response.status_code == 200
    matches = search_response.json()["matches"]
    match_names = [m["name"] for m in matches]
    assert "arm_official_kleidiai_bench" in match_names

    # 4. Execute tool call proxied to upstream server
    call_response = client.post(
        "/api/v1/registry/call",
        json={
            "name": "arm_official_hardware_telemetry",
            "arguments": {"cluster_id": "neoverse-n2-node-01"},
        },
    )
    assert call_response.status_code == 200
    call_data = call_response.json()
    assert call_data["result"]["status"] == "SUCCESS"
    assert "neoverse" in str(call_data).lower() or "upstream" in str(call_data).lower()
