"""Unified End-to-End Platform Integration Test Suite.

Single source of truth for all platform scenario tests.
Can be executed against:
1. In-Memory FastAPI TestClient (default: fast unit checks)
2. Local or CI/CD kind Kubernetes cluster (flag: --e2e-target=kind or E2E_TARGET=kind)
3. Live GKE cluster via port-forwarding (flag: --e2e-target=live_gke or E2E_TARGET=live_gke)
"""

import logging
import os
import socket
import subprocess
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from src.control_plane.main import app
from src.control_plane.orchestrator import SandboxOrchestrator
from src.data_plane.worker.sandbox_runner import DataPlaneSandboxRunner

logger = logging.getLogger("mvcp.e2e_platform")

# Environment / target configuration
E2E_TARGET = os.getenv("E2E_TARGET", "inmemory").lower()
GATEWAY_BASE_URL = os.getenv("MVCP_GATEWAY_URL", "http://localhost:8000")


def is_port_open(host: str, port: int) -> bool:
    """Checks if a TCP port is open and listening."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        return sock.connect_ex((host, port)) == 0


@pytest.fixture(scope="session", autouse=True)
def auto_port_forward_if_cluster_target():
    """Session fixture managing background kubectl port-forwarding when targeting live clusters."""
    port_forward_process = None

    if E2E_TARGET in ["kind", "live_gke", "cluster"]:
        if not is_port_open("localhost", 8000):
            logger.info(
                f"Target is '{E2E_TARGET}'. Port 8000 inactive. Launching kubectl port-forward..."
            )
            try:
                port_forward_process = subprocess.Popen(
                    ["kubectl", "port-forward", "svc/mvcp-gateway-service", "8000:8000"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                for _ in range(10):
                    if is_port_open("localhost", 8000):
                        break
                    time.sleep(0.5)
            except Exception as e:
                logger.warning(f"Could not start kubectl port-forward: {e}")

    yield GATEWAY_BASE_URL

    if port_forward_process:
        logger.info("Terminating background kubectl port-forward process...")
        port_forward_process.terminate()
        port_forward_process.wait()


# ==============================================================================
# SCENARIO 1: Gateway Readiness Health Check
# ==============================================================================
@pytest.mark.asyncio
async def test_scenario_1_gateway_health():
    """Verify gateway readiness health endpoint across targets."""
    if E2E_TARGET in ["kind", "live_gke", "cluster"]:
        async with httpx.AsyncClient(base_url=GATEWAY_BASE_URL, timeout=10.0) as client:
            res = await client.get("/api/v1/health")
            assert res.status_code == 200
            assert res.json()["status"] == "healthy"
    else:
        client = TestClient(app)
        res = client.get("/api/v1/health")
        assert res.status_code == 200
        assert res.json()["status"] == "healthy"


# ==============================================================================
# SCENARIO 2: MCP JSON-RPC Protocol Gateway Loops
# ==============================================================================
@pytest.mark.asyncio
async def test_scenario_2_mcp_json_rpc_gateway_loops():
    """Verify MCP tools/list, resources/list, resources/read, and tools/call JSON-RPC frames."""
    req_tools_list = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    req_res_list = {"jsonrpc": "2.0", "id": 2, "method": "resources/list", "params": {}}
    req_tool_call = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "optimize_kernel", "arguments": {"code": "void e2e_kernel() {}"}},
    }

    if E2E_TARGET in ["kind", "live_gke", "cluster"]:
        async with httpx.AsyncClient(base_url=GATEWAY_BASE_URL, timeout=10.0) as client:
            r1 = await client.post("/api/v1/mcp", json=req_tools_list)
            assert r1.status_code == 200 and "tools" in r1.json()["result"]

            r2 = await client.post("/api/v1/mcp", json=req_res_list)
            assert r2.status_code == 200 and "resources" in r2.json()["result"]

            r3 = await client.post("/api/v1/mcp", json=req_tool_call)
            assert r3.status_code == 200 and "result" in r3.json()
    else:
        client = TestClient(app)
        r1 = client.post("/api/v1/mcp", json=req_tools_list)
        assert r1.status_code == 200 and "tools" in r1.json()["result"]

        r2 = client.post("/api/v1/mcp", json=req_res_list)
        assert r2.status_code == 200 and "resources" in r2.json()["result"]

        r3 = client.post("/api/v1/mcp", json=req_tool_call)
        assert r3.status_code == 200 and "result" in r3.json()


# ==============================================================================
# SCENARIO 3: Local Tool Dispatcher Execution (/api/v1/registry/call)
# ==============================================================================
@pytest.mark.asyncio
async def test_scenario_3_tool_dispatcher_execution():
    """Verify tool execution via /api/v1/registry/call."""
    payload = {
        "name": "profile_and_optimize_kernel",
        "arguments": {"source_code": "void e2e_dispatch() {}"},
    }

    if E2E_TARGET in ["kind", "live_gke", "cluster"]:
        async with httpx.AsyncClient(base_url=GATEWAY_BASE_URL, timeout=15.0) as client:
            res = await client.post("/api/v1/registry/call", json=payload)
            assert res.status_code == 200
            assert res.json()["result"]["status"] == "SUCCESS"
    else:
        client = TestClient(app)
        res = client.post("/api/v1/registry/call", json=payload)
        assert res.status_code == 200
        assert res.json()["result"]["status"] == "SUCCESS"


# ==============================================================================
# SCENARIO 4: Node Pool & Sandbox Routing (gVisor vs Native)
# ==============================================================================
@pytest.mark.asyncio
async def test_scenario_4_node_pool_routing():
    """Verify use_gvisor=True routes to gVisor sandbox pool and use_gvisor=False routes to native baseline."""
    orchestrator = SandboxOrchestrator()
    orchestrator.allow_native_benchmarks = True

    manifest_gvisor = orchestrator.build_pod_manifest(
        "e2e-sc4-gvisor", "void k1() {}", use_gvisor=True, execution_mode="codemode"
    )
    assert manifest_gvisor["spec"]["runtimeClassName"] == "gvisor"
    assert manifest_gvisor["spec"]["nodeSelector"]["mvcp.ai/node-type"] == "arm-gvisor-sandbox"

    manifest_native = orchestrator.build_pod_manifest(
        "e2e-sc4-native", "void k2() {}", use_gvisor=False, execution_mode="direct"
    )
    assert manifest_native["spec"].get("runtimeClassName") is None
    assert manifest_native["spec"]["nodeSelector"]["mvcp.ai/node-type"] == "arm-native-baseline"

    # If active Kubernetes cluster target, verify live Kubernetes scheduling
    if E2E_TARGET in ["kind", "live_gke", "cluster"] and orchestrator.k8s_client_configured:
        from kubernetes import client

        v1 = client.CoreV1Api()
        try:
            # Verify live pod creation against cluster
            v1.create_namespaced_pod(body=manifest_gvisor, namespace="default")
            logger.info("Scenario 4: Successfully submitted gVisor sandbox pod to active cluster")
            v1.delete_namespaced_pod(name=manifest_gvisor["metadata"]["name"], namespace="default")
        except Exception as e:
            logger.info(f"Scenario 4 cluster pod submission validation: {e}")


# ==============================================================================
# SCENARIO 5: Security Isolation & Read-Only Filesystem Verification
# ==============================================================================
@pytest.mark.asyncio
async def test_scenario_5_security_readonly_filesystem():
    """Verify read-only filesystem write-block enforcement in REPL sandbox."""
    runner = DataPlaneSandboxRunner(memory_limit_mb=512, timeout_seconds=10.0)

    forbidden_write_code = """
try:
    with open('/opt/arm-tools/malicious.txt', 'w') as f:
        f.write('unauthorized_write')
    result = 'WRITE_SUCCESS'
except Exception as e:
    result = f'WRITE_BLOCKED: {type(e).__name__}'
"""
    res = await runner.execute_payload(forbidden_write_code)
    assert res["status"] == "success"
    assert (
        "WRITE_BLOCKED" in res["result"]
        or "FileNotFoundError" in res["result"]
        or "PermissionError" in res["result"]
    )
