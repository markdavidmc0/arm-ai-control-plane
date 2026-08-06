"""Unit tests for MontyEngine SFI sandboxed execution and configuration provisioning."""

from unittest.mock import patch

import pytest

from src.config import Settings
from src.data_plane.engines.monty_engine import MontyEngine
from src.data_plane.worker import LocalToolDispatcher


@pytest.mark.asyncio
@pytest.mark.unit
async def test_monty_engine_snippet_execution():
    """Evaluates math/string snippets with input dictionaries."""
    engine = MontyEngine()
    code = "x * 2 + y"
    inputs = {"x": 20, "y": 2}

    res = await engine.execute_snippet(code, inputs=inputs)

    assert res["success"] is True
    assert res["duration_ms"] >= 0.0
    assert res["error"] is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_monty_engine_external_function_callbacks():
    """Executes sandboxed code calling host function callbacks."""
    engine = MontyEngine()

    async def mock_get_data(id_val: int) -> dict[str, int]:
        return {"id": id_val, "value": 100}

    code = "get_data(123)"
    callbacks = {"get_data": mock_get_data}

    res = await engine.execute_snippet(code, external_functions=callbacks)

    assert res["success"] is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_monty_engine_stdout_capture():
    """Runs code containing print statements and verifies stdout capture."""
    engine = MontyEngine()
    code = 'print("hello SFI")'

    res = await engine.execute_snippet(code)

    assert res["success"] is True
    assert res["stdout"] == "hello SFI\n"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_monty_engine_resource_limit_breach():
    """Executes infinite loop while True: pass and verifies limits trap RuntimeError."""
    engine = MontyEngine()
    code = "while True:\n    pass"

    res = await engine.execute_snippet(code)

    assert res["success"] is False
    assert res["result"] is None
    err_msg = res["error"]["message"].lower()
    assert "limit" in err_msg or "timeout" in err_msg


@pytest.mark.asyncio
@pytest.mark.unit
async def test_monty_engine_syntax_error_handling():
    """Passes invalid code and verifies structured SyntaxError response."""
    engine = MontyEngine()
    code = "def invalid_syntax("

    res = await engine.execute_snippet(code)

    assert res["success"] is False
    assert res["result"] is None
    assert res["error"] is not None
    assert res["error"]["type"] == "SyntaxError"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_config_toggle_disable():
    """Mocks ENABLE_CODE_MODE=False and verifies repl_execute is excluded."""
    mock_settings = Settings(ENABLE_CODE_MODE=False)
    dispatcher = LocalToolDispatcher()

    with patch("src.data_plane.worker.settings", mock_settings):
        catalog = await dispatcher.read_catalog()
        tool_names = [t["name"] for t in catalog]
        assert "repl_execute" not in tool_names
        assert "execute_code" in tool_names
