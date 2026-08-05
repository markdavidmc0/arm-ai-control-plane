"""Unit tests for DataPlaneSandboxRunner in Data Plane.

Verifies CodeMode Python script payload execution, REPL state retention across turns,
timeout limits, memory bounds, and user identity/scope validation.
"""

import pytest

from src.data_plane.schemas import DataPlaneUserContext
from src.data_plane.worker import DataPlaneSandboxRunner


@pytest.mark.asyncio
@pytest.mark.unit
async def test_repl_code_execution_and_state_retention():
    """Verify basic python payload execution and state retention across multiple turns."""
    runner = DataPlaneSandboxRunner(memory_limit_mb=512, timeout_seconds=10.0)
    user_ctx = DataPlaneUserContext(
        user_id="usr_repl_test", role="developer", scopes=["tools:execute"]
    )

    turn1_code = "count = 42\nresult = 'turn1_ok'"
    res1 = await runner.execute_payload(turn1_code, user_context=user_ctx)

    assert res1["status"] == "success"
    assert res1["result"] == "turn1_ok"
    assert res1["updated_repl_state"].get("count") == 42
    assert res1["memory_limit_mb"] == 512

    turn2_code = "count += 10\nresult = f'count_is_{count}'"
    res2 = await runner.execute_payload(
        turn2_code, repl_state=res1["updated_repl_state"], user_context=user_ctx
    )

    assert res2["status"] == "success"
    assert res2["result"] == "count_is_52"
    assert res2["updated_repl_state"].get("count") == 52


@pytest.mark.asyncio
@pytest.mark.unit
async def test_repl_timeout_limit():
    """Verify execution exceeding timeout_seconds returns error status."""
    runner = DataPlaneSandboxRunner(memory_limit_mb=512, timeout_seconds=0.1)

    slow_code = "await asyncio.sleep(2.0)"
    res = await runner.execute_payload(slow_code)

    assert res["status"] == "error"
    assert "timed out" in res["error"].lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_repl_user_context_propagation():
    """Verify DataPlaneUserContext is validated and made available inside REPL execution."""
    runner = DataPlaneSandboxRunner(memory_limit_mb=256, timeout_seconds=10.0)
    user_ctx = DataPlaneUserContext(
        user_id="usr_scope_check", role="admin", scopes=["tools:execute", "admin:write"]
    )

    code = "result = f'{__user_context__.user_id}:{__user_context__.role}'"
    res = await runner.execute_payload(code, user_context=user_ctx)

    assert res["status"] == "success"
    assert res["result"] == "usr_scope_check:admin"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_repl_unauthorized_scope_rejection():
    """Verify execution fails or returns error if user context lacks required execution scope."""
    runner = DataPlaneSandboxRunner(memory_limit_mb=256, timeout_seconds=10.0)
    restricted_ctx = DataPlaneUserContext(
        user_id="usr_restricted", role="guest", scopes=["read_only"]
    )

    code = "result = 'should_not_run'"
    res = await runner.execute_payload(code, user_context=restricted_ctx)

    assert res["status"] == "error"
    assert "unauthorized" in res["error"].lower() or "scope" in res["error"].lower()
