"""Unit tests for DataPlaneSandboxRunner and REPL tool dispatching in Data Plane.

Verifies process-isolated REPL execution (child_pid != host_pid), contextlib.redirect_stdout safety,
multi-turn REPL state persistence, timeout bounds, and lack of synthetic PMU mock counters.
"""

import os

import pytest

from src.data_plane.schemas import DataPlaneUserContext
from src.data_plane.worker import DataPlaneSandboxRunner, LocalToolDispatcher


@pytest.mark.asyncio
@pytest.mark.unit
async def test_repl_executes_in_separate_process():
    """Verify code execution occurs inside a separate process ID from host process."""
    runner = DataPlaneSandboxRunner(timeout_seconds=5.0)
    user_ctx = DataPlaneUserContext(
        user_id="usr_repl_test", role="developer", scopes=["tools:execute"]
    )
    code = "import os\nresult = os.getpid()"

    res = await runner.execute_payload(code, user_context=user_ctx)

    assert res["status"] == "success"
    child_pid = res["result"]
    assert child_pid != os.getpid(), f"Execution PID {child_pid} matched host PID {os.getpid()}"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_repl_code_execution_stdout_safety():
    """Verify print() output is safely captured without breaking JSON parsing or mock counters."""
    runner = DataPlaneSandboxRunner(timeout_seconds=5.0)
    dispatcher = LocalToolDispatcher(sandbox_runner=runner)
    user_ctx = DataPlaneUserContext(
        user_id="usr_repl_test", role="developer", scopes=["tools:execute"]
    )

    code = "print('hello world')\nresult = 1 + 1"
    res = await dispatcher.dispatch_tool_call(
        "repl_execute", {"code": code}, user_context=user_ctx
    )

    assert res["jsonrpc"] == "2.0"
    assert "result" in res
    result_payload = res["result"]
    assert result_payload["status"] == "SUCCESS"
    assert "arm_pmu_counters" not in result_payload
    assert result_payload.get("output") == 2 or result_payload.get("result") == 2


@pytest.mark.asyncio
@pytest.mark.unit
async def test_repl_state_persistence_multi_turn():
    """Verify variables set in Turn 1 persist into Turn 2 REPL execution."""
    runner = DataPlaneSandboxRunner(timeout_seconds=5.0)
    dispatcher = LocalToolDispatcher(sandbox_runner=runner)
    user_ctx = DataPlaneUserContext(
        user_id="usr_repl_test", role="developer", scopes=["tools:execute"]
    )

    turn1_code = "x = 42\nresult = 'turn1_ok'"
    res1 = await dispatcher.dispatch_tool_call(
        "repl_execute", {"code": turn1_code}, user_context=user_ctx
    )

    assert res1["jsonrpc"] == "2.0"
    assert res1["result"]["status"] == "SUCCESS"
    updated_state = res1["result"].get("updated_repl_state", {})
    assert updated_state.get("x") == 42

    turn2_code = "result = x + 1"
    res2 = await dispatcher.dispatch_tool_call(
        "repl_execute",
        {"code": turn2_code, "repl_state": updated_state},
        user_context=user_ctx,
    )

    assert res2["jsonrpc"] == "2.0"
    assert res2["result"]["status"] == "SUCCESS"
    assert res2["result"]["output"] == 43 or res2["result"]["result"] == 43


@pytest.mark.asyncio
@pytest.mark.unit
async def test_repl_infinite_loop_timeout():
    """Verify infinite loop execution times out quickly and returns JSON-RPC -32603 error."""
    runner = DataPlaneSandboxRunner(timeout_seconds=0.1)
    dispatcher = LocalToolDispatcher(sandbox_runner=runner, timeout_seconds=0.1)

    res = await dispatcher.dispatch_tool_call(
        "repl_execute", {"code": "while True:\n    pass"}
    )

    assert res["jsonrpc"] == "2.0"
    assert "error" in res
    assert res["error"]["code"] == -32603
    assert "Execution timed out" in res["error"]["message"]
