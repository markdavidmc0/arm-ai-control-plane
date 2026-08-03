"""Integration tests for Pattern A RPC Dispatcher Bridge and /api/v1/registry/call route."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from src.control_plane.main import app
from src.data_plane.worker.sandbox_runner import DataPlaneSandboxRunner
from src.data_plane.worker.tool_dispatcher import LocalToolDispatcher

client = TestClient(app)


@pytest.mark.asyncio
async def test_local_tool_dispatcher_compiler_kernel(monkeypatch, tmp_path):
    """Verify LocalToolDispatcher dispatches kernel compilation profiler tool calls via local binary driver."""
    tools_dir = str(tmp_path)
    driver_file = tmp_path / "compiler_driver"
    driver_file.write_text("#!/bin/sh\nexit 0")
    driver_file.chmod(0o755)

    async def mock_subprocess(*args, **kwargs):
        class MockProcess:
            async def communicate(self):
                return (b'{"status": "success", "sme2_utilization_pct": 82.4}', b"")

        return MockProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_subprocess)

    dispatcher = LocalToolDispatcher(tools_dir=tools_dir)
    res = await dispatcher.dispatch_tool_call(
        "profile_and_optimize_kernel", {"source_code": "void matmul() {}"}
    )

    assert res["jsonrpc"] == "2.0"
    assert res["result"]["status"] == "SUCCESS"
    assert "profile_details" in res["result"]


@pytest.mark.asyncio
async def test_local_tool_dispatcher_search_meta_tool(tmp_path):
    """Verify LocalToolDispatcher dispatches mcp__search_tools meta-tool calls against catalog.json."""
    tools_dir = str(tmp_path)
    catalog_file = tmp_path / "catalog.json"
    import json

    catalog_file.write_text(
        json.dumps(
            {
                "tools": [
                    {
                        "name": "vectorization_tool",
                        "description": "Arm SIMD auto-vectorization optimizer",
                    }
                ]
            }
        )
    )

    dispatcher = LocalToolDispatcher(tools_dir=tools_dir)
    res = await dispatcher.dispatch_tool_call("mcp__search_tools", {"query": "vectorization"})

    assert res["jsonrpc"] == "2.0"
    assert res["result"]["status"] == "SUCCESS"
    assert len(res["result"]["matches"]) == 1
    assert res["result"]["matches"][0]["name"] == "vectorization_tool"


def test_mcp_registry_call_endpoint():
    """Verify /api/v1/registry/call routes through LocalToolDispatcher."""
    payload = {
        "name": "profile_and_optimize_kernel",
        "arguments": {"source_code": "void matmul() {}"},
    }
    response = client.post("/api/v1/registry/call", json=payload)

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
