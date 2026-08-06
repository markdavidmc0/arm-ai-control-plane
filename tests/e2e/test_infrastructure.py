"""Deterministic Infrastructure & Plumbing Test Suite.

Validates pod manifests, read-only volume mounts, gVisor security probes,
in-sandbox arm_tools module imports, and gateway/sidecar service reachability.
Requires zero live LLM API calls and completes in under 5 seconds.
"""

import logging

import pytest
from src.control_plane.orchestrator import SandboxOrchestrator

from src.data_plane.worker import DataPlaneSandboxRunner

logger = logging.getLogger("mvcp.e2e.infrastructure")


# ==============================================================================
# 1. Gateway & Service Reachability Checks
# ==============================================================================


@pytest.mark.asyncio
async def test_gateway_health_and_sidecar_reachability(api_client):
    """Assert control plane gateway readiness and health status."""
    res = await api_client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_control_plane_mcp_and_registry_routing(api_client):
    """Validate gateway MCP JSON-RPC protocol handling and tool execution routing."""
    tools_list_req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {},
    }
    mcp_res = await api_client.post("/api/v1/mcp", json=tools_list_req)
    assert mcp_res.status_code == 200
    assert "tools" in mcp_res.json()["result"]

    call_req = {
        "name": "profile_and_optimize_kernel",
        "arguments": {"source_code": "void infra_check() {}"},
    }
    call_res = await api_client.post("/api/v1/registry/call", json=call_req)
    assert call_res.status_code == 200
    assert call_res.json()["result"]["status"] == "SUCCESS"


# ==============================================================================
# 2. Pod Spec, Mount Verification & Node Routing
# ==============================================================================


@pytest.mark.asyncio
async def test_orchestrator_pod_spec_and_mounts(target_env):
    """Assert pod spec contains tools-installer initContainer and read-only /opt/arm-tools mount."""
    orchestrator = SandboxOrchestrator()
    manifest = orchestrator.build_pod_manifest(
        task_id="infra-mounts-001",
        cxx_code="void kernel() {}",
        use_gvisor=True,
        execution_mode="codemode",
    )

    spec = manifest["spec"]
    init_containers = spec.get("initContainers", [])
    assert len(init_containers) == 1
    installer = init_containers[0]
    assert installer["name"] == "tools-installer"
    assert "arm-workspace-tools" in installer["image"]

    container = spec["containers"][0]
    volume_mounts = container.get("volumeMounts", [])
    assert len(volume_mounts) == 1
    mount = volume_mounts[0]
    assert mount["mountPath"].rstrip("/") == "/opt/arm-tools"
    assert mount["readOnly"] is True

    if target_env in ["kind", "live_gke", "cluster"] and orchestrator.k8s_client_configured:
        from kubernetes import client

        v1 = client.CoreV1Api()
        try:
            v1.create_namespaced_pod(body=manifest, namespace="default")
            v1.delete_namespaced_pod(name=manifest["metadata"]["name"], namespace="default")
        except Exception as e:
            logger.warning(f"Infrastructure cluster pod creation test notice: {e}")


@pytest.mark.asyncio
async def test_node_pool_sandbox_routing():
    """Assert routing for gVisor runtime and arm-native-baseline node pools."""
    orchestrator = SandboxOrchestrator()
    orchestrator.allow_native_benchmarks = True

    manifest_gvisor = orchestrator.build_pod_manifest(
        "infra-routing-gvisor", "void k1() {}", use_gvisor=True, execution_mode="codemode"
    )
    assert manifest_gvisor["spec"]["runtimeClassName"] == "gvisor"
    assert manifest_gvisor["spec"]["nodeSelector"]["mvcp.ai/node-type"] == "arm-gvisor-sandbox"

    manifest_native = orchestrator.build_pod_manifest(
        "infra-routing-native", "void k2() {}", use_gvisor=False, execution_mode="direct"
    )
    assert manifest_native["spec"].get("runtimeClassName") is None
    assert manifest_native["spec"]["nodeSelector"]["mvcp.ai/node-type"] == "arm-native-baseline"


# ==============================================================================
# 3. gVisor Security Probes & In-Sandbox Tool Import Probe
# ==============================================================================


@pytest.mark.asyncio
async def test_gvisor_sandbox_probes_and_tool_imports():
    """Execute gVisor probes for write blocks, socket blocks, and arm_tools import."""
    runner = DataPlaneSandboxRunner(memory_limit_mb=512, timeout_seconds=10.0)

    probe_script = """
results = {}

# Probe 1: Inspect arm_tools REPL global variable and attributes
try:
    results['arm_tools_imported'] = True
    results['arm_tools_symbols'] = [s for s in dir(arm_tools) if not s.startswith('_')]
except Exception as e:
    results['arm_tools_imported'] = False
    results['arm_tools_error'] = str(e)

# Probe 2: Read-Only Filesystem Write Block
try:
    with open('/opt/arm-tools/probe_write.tmp', 'w') as f:
        f.write('unauthorized')
    results['fs_write'] = 'ALLOWED'
except Exception as e:
    results['fs_write'] = f'BLOCKED:{type(e).__name__}'

# Probe 3: Raw Socket Creation Block (SOCK_RAW)
try:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)
    results['raw_socket'] = 'ALLOWED'
except Exception as e:
    results['raw_socket'] = f'BLOCKED:{type(e).__name__}'

result = results
"""
    res = await runner.execute_payload(probe_script)
    assert res["status"] == "success"
    probe_res = res["result"]

    assert probe_res["arm_tools_imported"] is True
    assert (
        "acall_tool" in probe_res["arm_tools_symbols"]
        or "call_tool" in probe_res["arm_tools_symbols"]
    )
    assert "BLOCKED" in probe_res["fs_write"]
    assert "BLOCKED" in probe_res["raw_socket"]
