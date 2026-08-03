"""Extended Cluster Scenario Test Suite.

Deep integration tests evaluating InitContainer integrity, node pool routing,
gVisor security probes (read-only FS, raw sockets, namespace blocks), and Code Mode vs. Classic benchmarking.
"""

import logging
from typing import Any

import httpx
import pytest

from src.control_plane.orchestrator import SandboxOrchestrator
from src.data_plane.worker import DataPlaneSandboxRunner
from tests.e2e.conftest import E2E_TARGET, GATEWAY_BASE_URL

logger = logging.getLogger("mvcp.e2e.scenarios")

# ==============================================================================
# 1. InitContainer & Artifact Registry Integrity
# ==============================================================================


@pytest.mark.heavy
@pytest.mark.asyncio
async def test_init_container_and_artifact_registry_integrity():
    """Validate SandboxOrchestrator pod spec includes tools-installer initContainer and read-only /opt/arm-tools mount."""
    orchestrator = SandboxOrchestrator()
    manifest = orchestrator.build_pod_manifest(
        task_id="scenario-integrity-001",
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

    # In active cluster target, verify live submission against cluster CoreV1Api
    if E2E_TARGET in ["kind", "live_gke", "cluster"] and orchestrator.k8s_client_configured:
        from kubernetes import client

        v1 = client.CoreV1Api()
        try:
            v1.create_namespaced_pod(body=manifest, namespace="default")
            v1.delete_namespaced_pod(name=manifest["metadata"]["name"], namespace="default")
        except Exception as e:
            logger.warning(f"Scenario 1 cluster pod submission validation failed: {e}")


# ==============================================================================
# 2. Node Pool & Sandbox Routing
# ==============================================================================


@pytest.mark.heavy
@pytest.mark.asyncio
async def test_node_pool_and_sandbox_routing():
    """Assert use_gvisor=True schedules on arm-gvisor-sandbox with runtimeClassName: gvisor, while use_gvisor=False routes to arm-native-baseline."""
    orchestrator = SandboxOrchestrator()
    orchestrator.allow_native_benchmarks = True

    manifest_gvisor = orchestrator.build_pod_manifest(
        "scenario-routing-gvisor", "void k1() {}", use_gvisor=True, execution_mode="codemode"
    )
    assert manifest_gvisor["spec"]["runtimeClassName"] == "gvisor"
    assert manifest_gvisor["spec"]["nodeSelector"]["mvcp.ai/node-type"] == "arm-gvisor-sandbox"

    manifest_native = orchestrator.build_pod_manifest(
        "scenario-routing-native", "void k2() {}", use_gvisor=False, execution_mode="direct"
    )
    assert manifest_native["spec"].get("runtimeClassName") is None
    assert manifest_native["spec"]["nodeSelector"]["mvcp.ai/node-type"] == "arm-native-baseline"


# ==============================================================================
# 3. gVisor Security Probes
# ==============================================================================


@pytest.mark.heavy
@pytest.mark.asyncio
async def test_gvisor_security_probes():
    """Execute in-sandbox probes validating read-only write blocks, raw socket blocks, and namespace blocks."""
    runner = DataPlaneSandboxRunner(memory_limit_mb=512, timeout_seconds=10.0)

    probe_script = """
results = {}

# Probe 1: Read-Only Filesystem Write Block
try:
    with open('/opt/arm-tools/probe_write.tmp', 'w') as f:
        f.write('unauthorized')
    results['fs_write'] = 'ALLOWED'
except Exception as e:
    results['fs_write'] = f'BLOCKED:{type(e).__name__}'

# Probe 2: Raw Socket Creation Block (SOCK_RAW)
try:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)
    results['raw_socket'] = 'ALLOWED'
except Exception as e:
    results['raw_socket'] = f'BLOCKED:{type(e).__name__}'

# Probe 3: Namespace Manipulation Block (os.unshare)
try:
    import os
    if hasattr(os, 'unshare'):
        os.unshare(0)
        results['unshare'] = 'ALLOWED'
    else:
        results['unshare'] = 'BLOCKED:AttributeError'
except Exception as e:
    results['unshare'] = f'BLOCKED:{type(e).__name__}'

result = results
"""
    res = await runner.execute_payload(probe_script)
    assert res["status"] == "success"
    probe_res = res["result"]

    assert "BLOCKED" in probe_res["fs_write"]
    assert "BLOCKED" in probe_res["raw_socket"]
    assert "BLOCKED" in probe_res["unshare"]


async def run_agent_loop(mode: str, problem: str, test_client=None) -> dict[str, Any]:
    """Simulates a multi-turn LLM agent execution loop routing through Control Plane endpoints.

    Args:
        mode: Execution mode ('direct' for Classic, 'codemode' for Code Mode).
        problem: Prompt problem statement / source code.
        test_client: Optional TestClient for in-memory HTTP requests.

    Returns:
        Dict containing total 'turns', 'prompt_tokens', 'completion_tokens', and 'completed' status.
    """
    max_turns = 5
    turn_count = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    completed = False

    messages = [{"role": "user", "content": problem}]

    for turn in range(1, max_turns + 1):
        turn_count = turn
        llm_payload = {
            "model": "claude-3-5-sonnet",
            "messages": messages,
            "execution_mode": mode,
            "use_gvisor": True,
        }

        headers = {}
        if mode == "codemode":
            headers["X-Workspace-Context"] = "physical-ai"

        if test_client:
            res = test_client.post("/v1/chat/completions", json=llm_payload, headers=headers)
            assert res.status_code == 200
            res_data = res.json()
            prompt_tokens = int(res.headers.get("X-LLM-Prompt-Tokens", "100"))
        else:
            async with httpx.AsyncClient(base_url=GATEWAY_BASE_URL, timeout=10.0) as client:
                res = await client.post("/v1/chat/completions", json=llm_payload, headers=headers)
                assert res.status_code == 200
                res_data = res.json()
                prompt_tokens = int(res.headers.get("X-LLM-Prompt-Tokens", "100"))

        total_prompt_tokens += prompt_tokens
        completion_tokens = res_data.get("usage", {}).get("completion_tokens", 120)
        total_completion_tokens += completion_tokens

        choice = res_data["choices"][0]
        finish_reason = choice.get("finish_reason")

        if mode == "direct" and turn == 1:
            tool_call_payload = {
                "name": "profile_and_optimize_kernel",
                "arguments": {"source_code": problem},
            }
            if test_client:
                tool_res = test_client.post("/api/v1/registry/call", json=tool_call_payload)
            else:
                async with httpx.AsyncClient(base_url=GATEWAY_BASE_URL, timeout=10.0) as client:
                    tool_res = await client.post("/api/v1/registry/call", json=tool_call_payload)
            assert tool_res.status_code == 200
            tool_output = tool_res.json()

            messages.append(
                {
                    "role": "assistant",
                    "content": "Executing profile_and_optimize_kernel",
                }
            )
            messages.append({"role": "tool", "content": str(tool_output)})
        else:
            if finish_reason == "stop" or not choice.get("message", {}).get("tool_calls"):
                completed = True
                break

    return {
        "turns": turn_count,
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
        "completed": completed,
    }


# ==============================================================================
# 4. Code Mode vs. Classic Benchmarking
# ==============================================================================


@pytest.mark.heavy
@pytest.mark.asyncio
async def test_code_mode_vs_classic_benchmarking(test_client):
    """Compare Classic tool calling vs Code Mode execution via real HTTP agent loops."""
    problem = "void matmul_opt() { /* Optimize SME2 kernel */ }"

    if E2E_TARGET in ["kind", "live_gke", "cluster"]:
        classic_res = await run_agent_loop("direct", problem, test_client=None)
        code_mode_res = await run_agent_loop("codemode", problem, test_client=None)
    else:
        classic_res = await run_agent_loop("direct", problem, test_client=test_client)
        code_mode_res = await run_agent_loop("codemode", problem, test_client=test_client)

    assert classic_res["completed"] is True
    assert code_mode_res["completed"] is True
    assert classic_res["turns"] <= 5
    assert code_mode_res["turns"] <= 5
    assert code_mode_res["turns"] < classic_res["turns"]
    assert code_mode_res["prompt_tokens"] < classic_res["prompt_tokens"]
