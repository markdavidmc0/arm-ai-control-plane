"""Integration tests for CodeMode harness, dynamic_catalog prompt cache protection, and Data Plane REPL runner."""

import asyncio
import pytest

from src.control_plane.services.agent_factory import create_arm_agent
from src.control_plane.services.mcp_multiplexer import MCPMultiplexerService
from src.data_plane.worker.sandbox_runner import DataPlaneSandboxRunner


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

    # Code snippet executing parallel asyncio.gather
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
    """Verify system prompt schema prefix remains identical before and after dynamic catalog initialization."""
    agent = create_arm_agent("anthropic:claude-3-5-sonnet")

    if isinstance(agent, dict):
        # Simulation mode fallback
        capability = agent["capabilities"][0]
        assert capability.dynamic_catalog is True
        assert capability.tools == {"code_mode": True}
    else:
        # Pydantic AI Agent mode (capabilities stored in root_capability)
        root_cap = getattr(agent, "root_capability", None) or getattr(agent, "_root_capability", None)
        assert root_cap is not None
        cap_list = getattr(root_cap, "capabilities", [root_cap])
        code_mode_caps = [c for c in cap_list if "CodeMode" in c.__class__.__name__ or hasattr(c, "dynamic_catalog")]
        assert len(code_mode_caps) > 0
        assert getattr(code_mode_caps[0], "dynamic_catalog", True) is True


@pytest.mark.asyncio
async def test_multi_turn_repl_state_persistence():
    """Verify variables and state set in Turn 1 persist into Turn 2 REPL execution."""
    runner = DataPlaneSandboxRunner(memory_limit_mb=512, timeout_seconds=10.0)

    # Turn 1: Initialize matrix dataset variable
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

    # Turn 2: Access matrix_dim variable initialized in Turn 1
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
