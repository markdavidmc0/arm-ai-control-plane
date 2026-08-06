"""Unit tests for Data Plane catalog hot-reloading and execution dispatching."""

import json
import os
import time
from pathlib import Path

import pytest

from src.config import settings
from src.data_plane.worker import LocalToolDispatcher

# Determine the active base primitive expected in the environment
EXPECTED_BASE_TOOL = (
    "repl_execute" if getattr(settings, "ENABLE_CODE_MODE", False) else "execute_code"
)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_data_plane_cold_boot_safety(tmp_path: Path) -> None:
    """Verifies LocalToolDispatcher boots cleanly when catalog.json is missing."""
    tools_dir = tmp_path / "empty_tools_dir"
    dispatcher = LocalToolDispatcher(tools_dir=tools_dir)

    tools = await dispatcher.read_catalog()
    assert isinstance(tools, list)
    tool_names = [t.get("name") for t in tools]
    # Asserts the exact base tool active for the current environment setting
    assert EXPECTED_BASE_TOOL in tool_names


@pytest.mark.asyncio
@pytest.mark.unit
async def test_data_plane_built_in_and_dynamic_catalog_merging(tmp_path: Path) -> None:
    """Verifies catalog.json tools merge with built-in tools without hiding native handlers."""
    tools_dir = tmp_path / "tools_dir"
    tools_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = tools_dir / "catalog.json"

    custom_catalog = {
        "tools": [
            {
                "name": "arm_sme2_kernel",
                "description": "Custom Arm SME2 kernel",
                "parameters": {},
            }
        ]
    }
    catalog_path.write_text(json.dumps(custom_catalog), encoding="utf-8")

    dispatcher = LocalToolDispatcher(tools_dir=tools_dir)
    tools = await dispatcher.read_catalog()

    tool_names = [t.get("name") for t in tools]
    assert EXPECTED_BASE_TOOL in tool_names
    assert "arm_sme2_kernel" in tool_names


@pytest.mark.asyncio
@pytest.mark.unit
async def test_data_plane_hot_reloading_on_mtime_change(tmp_path: Path) -> None:
    """Verifies updating catalog.json st_mtime triggers automatic reloading."""
    tools_dir = tmp_path / "tools_dir"
    tools_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = tools_dir / "catalog.json"

    catalog_v1 = {"tools": [{"name": "tool_v1", "description": "Version 1"}]}
    catalog_path.write_text(json.dumps(catalog_v1), encoding="utf-8")

    dispatcher = LocalToolDispatcher(tools_dir=tools_dir)
    tools1 = await dispatcher.read_catalog()
    tool_names1 = [t.get("name") for t in tools1]
    assert "tool_v1" in tool_names1
    assert "tool_v2" not in tool_names1

    # Ensure mtime changes
    time.sleep(0.05)

    catalog_v2 = {
        "tools": [
            {"name": "tool_v1", "description": "Version 1"},
            {"name": "tool_v2", "description": "Version 2"},
        ]
    }
    catalog_path.write_text(json.dumps(catalog_v2), encoding="utf-8")
    # Touch mtime explicitly to ensure st_mtime increase
    new_mtime = catalog_path.stat().st_mtime + 1.0
    os.utime(catalog_path, (new_mtime, new_mtime))

    tools2 = await dispatcher.read_catalog()
    tool_names2 = [t.get("name") for t in tools2]
    assert "tool_v1" in tool_names2
    assert "tool_v2" in tool_names2


@pytest.mark.asyncio
@pytest.mark.unit
async def test_data_plane_error_isolation_corrupted_json(tmp_path: Path) -> None:
    """Verifies corrupt JSON writes log error and retain last valid cached catalog state."""
    tools_dir = tmp_path / "tools_dir"
    tools_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = tools_dir / "catalog.json"

    valid_catalog = {"tools": [{"name": "stable_tool", "description": "Last valid tool state"}]}
    catalog_path.write_text(json.dumps(valid_catalog), encoding="utf-8")

    dispatcher = LocalToolDispatcher(tools_dir=tools_dir)
    tools1 = await dispatcher.read_catalog()
    assert any(t.get("name") == "stable_tool" for t in tools1)

    time.sleep(0.05)
    # Write invalid corrupted JSON syntax
    catalog_path.write_text("{ corrupt_json: [ invalid_syntax", encoding="utf-8")
    new_mtime = catalog_path.stat().st_mtime + 1.0
    os.utime(catalog_path, (new_mtime, new_mtime))

    tools2 = await dispatcher.read_catalog()
    # Retains last valid cached catalog state
    assert any(t.get("name") == "stable_tool" for t in tools2)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_data_plane_native_host_fallback(tmp_path: Path) -> None:
    """Verifies tools with entrypoint=None dispatch to native in-memory handlers."""
    dispatcher = LocalToolDispatcher(tools_dir=tmp_path)

    res = await dispatcher.dispatch_tool_call(EXPECTED_BASE_TOOL, {"code": "1 + 1"})
    assert res.get("jsonrpc") == "2.0"
    assert "result" in res
    assert res["result"]["status"] == "SUCCESS"
    assert res["result"]["output"] == 2


@pytest.mark.asyncio
@pytest.mark.unit
async def test_data_plane_python_script_entrypoint_binding(tmp_path: Path) -> None:
    """Verifies .py script entrypoints execute via sys.executable."""
    tools_dir = tmp_path / "py_tools"
    tools_dir.mkdir(parents=True, exist_ok=True)

    script_path = tools_dir / "my_script.py"
    script_content = "import json, sys\nprint(json.dumps({'status': 'SUCCESS', 'result': 84}))\n"
    script_path.write_text(script_content, encoding="utf-8")

    catalog = {
        "tools": [
            {
                "name": "custom_python_tool",
                "description": "Custom Python script entrypoint tool",
                "entrypoint": "my_script.py",
            }
        ]
    }
    (tools_dir / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")

    dispatcher = LocalToolDispatcher(tools_dir=tools_dir)
    res = await dispatcher.dispatch_tool_call("custom_python_tool", {"param": "val"})

    assert res.get("jsonrpc") == "2.0"
    assert "result" in res
    assert res["result"]["tool_name"] == "custom_python_tool"
    assert res["result"]["status"] == "SUCCESS"
    assert res["result"]["output"]["result"] == 84


@pytest.mark.asyncio
@pytest.mark.unit
async def test_data_plane_binary_execution(tmp_path: Path) -> None:
    """Verifies executable binary dispatching via os.X_OK."""
    tools_dir = tmp_path / "bin_tools"
    tools_dir.mkdir(parents=True, exist_ok=True)

    bin_path = tools_dir / "my_bin"
    bin_output = json.dumps({"status": "SUCCESS", "binary_out": 100})
    bin_path.write_text(f"#!/bin/sh\necho '{bin_output}'\n", encoding="utf-8")
    bin_path.chmod(0o755)

    catalog = {
        "tools": [
            {
                "name": "custom_bin_tool",
                "description": "Custom binary entrypoint tool",
                "entrypoint": "my_bin",
            }
        ]
    }
    (tools_dir / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")

    dispatcher = LocalToolDispatcher(tools_dir=tools_dir)
    res = await dispatcher.dispatch_tool_call("custom_bin_tool", {})

    assert res.get("jsonrpc") == "2.0"
    assert "result" in res
    assert res["result"]["tool_name"] == "custom_bin_tool"
    assert res["result"]["status"] == "SUCCESS"
    assert res["result"]["output"]["binary_out"] == 100


@pytest.mark.asyncio
@pytest.mark.unit
async def test_data_plane_path_traversal_prevention(tmp_path: Path) -> None:
    """Verifies traversal attempts outside tools_dir return JSON-RPC code -32601 or -32602."""
    tools_dir = tmp_path / "secured_tools"
    tools_dir.mkdir(parents=True, exist_ok=True)

    catalog = {
        "tools": [
            {
                "name": "malicious_tool",
                "description": "Path traversal attempt",
                "entrypoint": "../../etc/passwd",
            }
        ]
    }
    (tools_dir / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")

    dispatcher = LocalToolDispatcher(tools_dir=tools_dir)
    res = await dispatcher.dispatch_tool_call("malicious_tool", {})

    assert res.get("jsonrpc") == "2.0"
    assert "error" in res
    assert res["error"]["code"] in [-32601, -32602]
    err_msg = res["error"]["message"].lower()
    assert "path traversal" in err_msg or "missing" in err_msg
