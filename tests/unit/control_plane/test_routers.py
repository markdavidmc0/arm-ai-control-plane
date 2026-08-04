"""Unit & Integration Test Suite for Control Plane APIRouters.

Verifies Zero-Trust Auth Guard & Keycloak OIDC, MCP Master Registry & Workspace Slicing,
and LLM Proxy completion header injection.
"""

from src.control_plane.services.auth_service import AuthService, hash_key

# ==============================================================================
# 1. Zero-Trust Auth Guard & Keycloak OIDC Tests
# ==============================================================================


def test_auth_check_missing_headers(test_client):
    """Verify auth-check fails with 401 when no key headers are provided."""
    response = test_client.get("/api/v1/internal/auth-check")
    assert response.status_code == 401
    assert response.json()["status"] == "DENIED"


def test_auth_check_judge_key_success(test_client):
    """Verify X-Judge-API-Key approves instant access and returns user headers."""
    response = test_client.get(
        "/api/v1/internal/auth-check",
        headers={"X-Judge-API-Key": "judge_secret_key_123"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"
    assert response.headers["X-User-Role"] == "judge"


def test_auth_check_bearer_key_success(test_client):
    """Verify Authorization: Bearer arm_dev_* key approves developer access."""
    response = test_client.get(
        "/api/v1/internal/auth-check",
        headers={"Authorization": "Bearer arm_dev_local_test_key_123"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"
    scopes_header = response.headers["X-User-Scopes"]
    assert "compiler" in scopes_header
    assert "autotuner" not in scopes_header
    assert "heatmap" not in scopes_header


def test_auth_check_invalid_key(test_client):
    """Verify invalid key returns 401 Unauthorized."""
    response = test_client.get(
        "/api/v1/internal/auth-check",
        headers={"Authorization": "Bearer arm_invalid_token_999"},
    )
    assert response.status_code == 401
    assert response.json()["status"] == "DENIED"


def test_salted_hash_computation():
    """Verify salted SHA-256 hash algorithm determinism."""
    digest1 = hash_key("test_key_abc", "salt1")
    digest2 = hash_key("test_key_abc", "salt1")
    digest3 = hash_key("test_key_abc", "salt2")

    assert digest1 == digest2
    assert digest1 != digest3
    assert len(digest1) == 64


def test_auth_service_rate_limiting():
    """Verify sliding-window rate limiter blocks after threshold is exceeded."""
    service = AuthService()
    test_id = "test_client_key_123"

    for _ in range(60):
        allowed, _ = service.check_rate_limit(test_id, role="judge")
        assert allowed is True

    allowed, count = service.check_rate_limit(test_id, role="judge")
    assert allowed is False
    assert count == 60


def test_keycloak_token_issuance_success(test_client):
    """Verify Keycloak M2M token endpoint returns OAuth2 JWT access token."""
    response = test_client.post(
        "/realms/arm-platform/protocol/openid-connect/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "github-ci-runner",
            "client_secret": "mcp_ci_runner_secret_2026",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] == 900


def test_keycloak_m2m_tool_registration_success(test_client):
    """Verify submitting domain-sliced tool payload using Keycloak Bearer JWT returns 200 OK."""
    token_res = test_client.post(
        "/realms/arm-platform/protocol/openid-connect/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "github-ci-runner",
            "client_secret": "mcp_ci_runner_secret_2026",
        },
    )
    access_token = token_res.json()["access_token"]

    payload = {
        "tools": [
            {
                "name": "vllm_arm_kv_cache_allocator_analyzer",
                "description": "Analyzes vLLM KV Cache allocation efficiency on Neoverse N2",
                "language": "python",
                "domain": "cloud-ai",
                "parameters": {"type": "object", "properties": {}},
            }
        ]
    }

    reg_res = test_client.post(
        "/api/v1/registry/register",
        json=payload,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert reg_res.status_code == 200
    assert reg_res.json()["status"] == "SUCCESS"
    assert reg_res.json()["registered_count"] == 1


def test_m2m_tool_registration_invalid_token(test_client):
    """Verify registration fails with HTTP 401 when an invalid JWT is provided."""
    payload = {
        "tools": [
            {
                "name": "invalid_tool",
                "domain": "cloud-ai",
                "parameters": {},
            }
        ]
    }

    response = test_client.post(
        "/api/v1/registry/register",
        json=payload,
        headers={"Authorization": "Bearer invalid_expired_jwt_token_999"},
    )
    assert response.status_code == 401


# ==============================================================================
# 2. MCP Master Registry & Workspace Slicing Tests
# ==============================================================================


def test_workspace_slicing_token_limit(test_client):
    """Verify workspace context slicing returns filtered tool list footprint (< 1,500 tokens)."""
    response = test_client.get(
        "/api/v1/registry/tools", headers={"X-Workspace-Context": "physical-ai"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["estimated_token_footprint"] < 1500
    assert data["workspace_context"] == "physical-ai"


def test_on_demand_search_meta_tool(test_client):
    """Test lazy-loaded mcp__search_tools meta-tool returning matching schemas."""
    response = test_client.post(
        "/api/v1/registry/search",
        json={"query": "voxelizer", "domain": "physical-ai"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["match_count"] >= 1
    assert "voxelizer" in data["matches"][0]["name"]


def test_gvisor_code_mode_execution(test_client):
    """Test script submission to /api/v1/sandbox/execute returning clean stdout output."""
    sample_script = "result = await arm_tools.profile_and_optimize_kernel(source_code='void matmul(){}'); print(result)"
    response = test_client.post(
        "/api/v1/sandbox/execute",
        json={"script": sample_script, "timeout_seconds": 10},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert len(data["stdout"]) > 0


def test_upstream_mcp_server_registration_and_search(test_client):
    """Test registering upstream MCP server, verifying handshake tool integration, search, and call proxying."""
    reg_response = test_client.post(
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

    tools_response = test_client.get(
        "/api/v1/registry/tools", headers={"X-Workspace-Context": "physical-ai"}
    )
    assert tools_response.status_code == 200
    tool_names = [t["name"] for t in tools_response.json()["tools"]]
    assert "arm_official_hardware_telemetry" in tool_names

    search_response = test_client.post(
        "/api/v1/registry/search", json={"query": "kleidiai", "domain": "base"}
    )
    assert search_response.status_code == 200
    matches = search_response.json()["matches"]
    match_names = [m["name"] for m in matches]
    assert "arm_official_kleidiai_bench" in match_names

    call_response = test_client.post(
        "/api/v1/registry/call",
        json={
            "name": "arm_official_hardware_telemetry",
            "arguments": {"cluster_id": "neoverse-n2-node-01"},
        },
    )
    assert call_response.status_code == 200
    call_data = call_response.json()
    assert call_data["result"]["status"] == "SUCCESS"


def test_keycloak_jwt_verification_valid():
    """Verify valid Keycloak OIDC JWT is correctly decoded and approved by AuthService."""
    service = AuthService()
    valid_jwt = service.mint_keycloak_jwt()
    payload = service.verify_jwt_token(valid_jwt)

    assert payload is not None
    assert payload["iss"] == "https://keycloak.internal/realms/arm-platform"
    assert "mcp-registrar" in payload["realm_access"]["roles"]


def test_keycloak_jwt_verification_expired():
    """Verify expired Keycloak OIDC JWT throws 401 / returns None."""
    import time
    service = AuthService()

    # Construct an expired JWT (exp set to 1 hour ago)
    header_b64 = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6ImtleWNsb2FrLW1hbC0xIn0"
    expired_payload = {
        "exp": int(time.time()) - 3600,
        "iss": "https://keycloak.internal/realms/arm-platform",
        "sub": "expired_m2m_runner",
    }
    import base64
    import json
    payload_b64 = base64.urlsafe_b64encode(json.dumps(expired_payload).encode()).decode().rstrip("=")
    expired_jwt = f"{header_b64}.{payload_b64}.mock_signature"

    payload = service.verify_jwt_token(expired_jwt)
    assert payload is None


# ==============================================================================
# 3. LLM Completion Proxy Tests
# ==============================================================================


def test_llm_proxy_headers(test_client):
    """Verify /v1/chat/completions injects X-LLM-Cost-USD and token metadata headers."""
    response = test_client.post(
        "/v1/chat/completions",
        json={
            "model": "claude-3-5-sonnet",
            "messages": [
                {
                    "role": "user",
                    "content": "Optimize SVE matrix multiplication kernel.",
                }
            ],
        },
    )
    assert response.status_code == 200
    assert "X-LLM-Cost-USD" in response.headers
    assert "X-LLM-Prompt-Tokens" in response.headers
    assert "X-LLM-Completion-Tokens" in response.headers
    assert "X-LLM-Latency-MS" in response.headers
    assert "X-LLM-Provider" in response.headers
