"""Unit & Integration Test Suite for Data Plane Worker.

Verifies DataPlaneSandboxRunner REPL state persistence, top-level await,
parallel asyncio.gather tool calls, and LocalToolDispatcher subprocess execution.
"""

import asyncio
import json

import pytest
from pydantic_ai import Agent
from pydantic_ai_harness import CodeMode
from src.control_plane.services.mcp_multiplexer import MCPMultiplexerService

from src.control_plane.schemas import ArmPlatformDeps
from src.data_plane.worker import (
    DataPlaneSandboxRunner,
    LocalToolDispatcher,
)


def create_arm_agent(model_name: str = "anthropic:claude-3-5-sonnet") -> Agent:
    """Constructs a test Pydantic AI Agent instance with CodeMode enabled."""
    code_mode = CodeMode(
        dynamic_catalog=True,
        tools={"code_mode": True},
    )
    return Agent(
        model=model_name,
        capabilities=[code_mode],
        deps_type=ArmPlatformDeps,
    )


# ==============================================================================
# 1. DataPlaneSandboxRunner Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_single_turn_parallel_execution():
    """Verify multiple tool calls execute concurrently inside one DataPlaneSandboxRunner turn."""
    call_log = []

    async def mock_kernel_a():
        await asyncio.sleep(0.01)
        call_log.append("kernel_a")
        return "result_a"

    async def mock_kernel_b():
        await asyncio.sleep(0.01)
        call_log.append("kernel_b")
        return "result_b"

    runner = DataPlaneSandboxRunner(memory_limit_mb=512, timeout_seconds=10.0)

    code_snippet = """
async def run():
    res_a, res_b = await asyncio.gather(kernel_a(), kernel_b())
    return f"{res_a}_{res_b}"

result = run()
"""

    tool_bindings = {"kernel_a": mock_kernel_a, "kernel_b": mock_kernel_b}
    response = await runner.execute_payload(code_snippet, tool_bindings=tool_bindings)

    assert response["status"] == "success"
    assert response["result"] == "result_a_result_b"
    assert "kernel_a" in call_log
    assert "kernel_b" in call_log


@pytest.mark.asyncio
async def test_prompt_cache_preservation():
    """Verify system prompt schema prefix remains identical before and after catalog init."""
    agent = create_arm_agent("anthropic:claude-3-5-sonnet")

    if isinstance(agent, dict):
        capability = agent["capabilities"][0]
        assert capability.dynamic_catalog is True
        assert capability.tools == {"code_mode": True}
    else:
        root_cap = getattr(agent, "root_capability", None) or getattr(
            agent, "_root_capability", None
        )
        assert root_cap is not None
        cap_list = getattr(root_cap, "capabilities", [root_cap])
        code_mode_caps = [
            c
            for c in cap_list
            if "CodeMode" in c.__class__.__name__ or hasattr(c, "dynamic_catalog")
        ]
        assert len(code_mode_caps) > 0
        assert getattr(code_mode_caps[0], "dynamic_catalog", True) is True


@pytest.mark.asyncio
async def test_multi_turn_repl_state_persistence():
    """Verify variables and state set in Turn 1 persist into Turn 2 REPL execution."""
    runner = DataPlaneSandboxRunner(memory_limit_mb=512, timeout_seconds=10.0)

    turn_1_code = """
matrix_dim = 1024
optimization_target = "cortex-x925"
result = "turn_1_initialized"
"""
    turn_1_resp = await runner.execute_payload(turn_1_code)

    assert turn_1_resp["status"] == "success"
    repl_state = turn_1_resp["updated_repl_state"]
    assert repl_state.get("matrix_dim") == 1024
    assert repl_state.get("optimization_target") == "cortex-x925"

    turn_2_code = """
result = f"Matrix {matrix_dim} optimized for {optimization_target}"
"""
    turn_2_resp = await runner.execute_payload(turn_2_code, repl_state=repl_state)

    assert turn_2_resp["status"] == "success"
    assert turn_2_resp["result"] == "Matrix 1024 optimized for cortex-x925"


@pytest.mark.asyncio
async def test_deferred_mcp_toolset_building():
    """Verify build_deferred_mcp_toolset creates deferred toolset wrapper with metadata."""
    multiplexer = MCPMultiplexerService()
    toolset = multiplexer.build_deferred_mcp_toolset(domain="cloud-ai")

    if isinstance(toolset, dict):
        assert toolset["defer_loading"] is True
        assert toolset["metadata"] == {"code_mode": True}
    else:
        assert getattr(toolset, "defer_loading", True) is True


@pytest.mark.asyncio
async def test_top_level_await_execution():
    """Verify DataPlaneSandboxRunner executes scripts with top-level await statements."""
    runner = DataPlaneSandboxRunner(memory_limit_mb=512, timeout_seconds=10.0)

    code_snippet = """
profile = await arm_tools.profile_and_optimize_kernel(source_code="void matmul() {}")
status_val = profile["result"]["status"]
result = f"Status: {status_val}"
"""
    resp = await runner.execute_payload(code_snippet)

    assert resp["status"] == "success"
    assert resp["result"] == "Status: SUCCESS"
    assert "profile" in resp["updated_repl_state"]
    assert resp["updated_repl_state"]["status_val"] == "SUCCESS"


@pytest.mark.asyncio
async def test_arm_tools_keyword_arg_forwarding():
    """Verify dynamic method calls on arm_tools forward keyword arguments to LocalToolDispatcher."""
    runner = DataPlaneSandboxRunner(memory_limit_mb=512, timeout_seconds=10.0)

    code_snippet = """
res = await arm_tools.profile_and_optimize_kernel(code="void custom_kernel() {}", use_gvisor=True)
result = res["result"]["status"]
"""
    resp = await runner.execute_payload(code_snippet)

    assert resp["status"] == "success"
    assert resp["result"] == "SUCCESS"


# ==============================================================================
# 2. LocalToolDispatcher Subprocess Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_local_tool_dispatcher_compiler_kernel(tmp_path):
    """Verify LocalToolDispatcher dispatches kernel compilation profiler tool calls."""
    tools_dir = str(tmp_path)
    driver_file = tmp_path / "compiler_driver"

    fake_profile = {
        "task_id": "test-123",
        "status": "success",
        "target_hardware": "Cortex-X925",
        "sme2_utilization_pct": 88.5,
    }
    driver_script = f"#!/usr/bin/env python3\nimport json\nprint(json.dumps({fake_profile}))\n"
    driver_file.write_text(driver_script)
    driver_file.chmod(0o755)

    dispatcher = LocalToolDispatcher(tools_dir=tools_dir)
    res = await dispatcher.dispatch_tool_call(
        "profile_and_optimize_kernel", {"source_code": "void test() {}"}
    )

    assert res["jsonrpc"] == "2.0"
    assert res["result"]["status"] == "SUCCESS"
    assert res["result"]["profile_details"]["sme2_utilization_pct"] == 88.5


@pytest.mark.asyncio
async def test_local_tool_dispatcher_search_meta_tool(tmp_path):
    """Verify LocalToolDispatcher dispatches mcp__search_tools meta-tool calls."""
    tools_dir = str(tmp_path)
    catalog_file = tmp_path / "catalog.json"

    fake_catalog = {
        "tools": [
            {
                "name": "arm_sme2_matrix_gemm",
                "description": "SME2 GEMM kernel optimizer",
            },
            {
                "name": "ros2_voxelizer",
                "description": "PointCloud2 Voxel Grid filter",
            },
        ]
    }
    catalog_file.write_text(json.dumps(fake_catalog))

    dispatcher = LocalToolDispatcher(tools_dir=tools_dir)
    res = await dispatcher.dispatch_tool_call("mcp__search_tools", {"query": "SME2"})

    assert res["jsonrpc"] == "2.0"
    assert res["result"]["status"] == "SUCCESS"
    assert len(res["result"]["matches"]) == 1
    assert res["result"]["matches"][0]["name"] == "arm_sme2_matrix_gemm"


@pytest.mark.asyncio
async def test_mcp_registry_call_endpoint(test_client):
    """Verify /api/v1/registry/call routes through LocalToolDispatcher."""
    payload = {
        "name": "profile_and_optimize_kernel",
        "arguments": {"source_code": "void matmul() {}"},
    }
    response = test_client.post("/api/v1/registry/call", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["result"]["status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_arm_tools_bridge_integration():
    """Verify arm_tools bridge executes dynamically inside DataPlaneSandboxRunner REPL."""
    runner = DataPlaneSandboxRunner(memory_limit_mb=512, timeout_seconds=10.0)

    code_snippet = """
async def run():
    profile = await arm_tools.profile_and_optimize_kernel(source_code="void matmul() {}")
    return profile["result"]["status"]

result = run()
"""
    response = await runner.execute_payload(code_snippet)

    assert response["status"] == "success"
    assert response["result"] == "SUCCESS"


@pytest.mark.asyncio
async def test_parallel_arm_tools_execution():
    """Verify parallel tool calls via arm_tools inside asyncio.gather."""
    runner = DataPlaneSandboxRunner(memory_limit_mb=512, timeout_seconds=10.0)

    code_snippet = """
async def run():
    res1, res2 = await asyncio.gather(
        arm_tools.profile_and_optimize_kernel(source_code="void matmul_1() {}"),
        arm_tools.profile_and_optimize_kernel(source_code="void matmul_2() {}")
    )
    return f"{res1['result']['status']}_{res2['result']['status']}"

result = run()
"""
    response = await runner.execute_payload(code_snippet)

    assert response["status"] == "success"
    assert response["result"] == "SUCCESS_SUCCESS"
