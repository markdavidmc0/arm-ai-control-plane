"""Unit tests for LocalToolDispatcher in Data Plane.

Verifies path canonicalization / path traversal prevention (-32602),
direct vector subprocess execution, timeout and process failure error mapping (-32603),
catalog discovery, and search_tools meta-tool functionality.
"""

import json

import pytest

from src.data_plane.schemas import DataPlaneUserContext
from src.data_plane.worker import LocalToolDispatcher


@pytest.mark.asyncio
@pytest.mark.unit
async def test_path_traversal_prevention_dot_dot(tmp_path):
    """Verify path traversal attempts (e.g. ../../../bin/sh) return -32602 Invalid Params."""
    tools_dir = str(tmp_path)
    dispatcher = LocalToolDispatcher(tools_dir=tools_dir)

    traversal_targets = [
        "../../../bin/sh",
        "../../etc/passwd",
        "../test_file",
        "/etc/passwd",
    ]

    for target in traversal_targets:
        res = await dispatcher.dispatch_tool_call(target, {"arg": "val"})
        assert res["jsonrpc"] == "2.0"
        assert "error" in res
        assert res["error"]["code"] == -32602
        assert (
            "Invalid Params" in res["error"]["message"]
            or "path traversal" in res["error"]["message"].lower()
        )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_subprocess_vector_execution(tmp_path):
    """Verify valid binary executes via direct vector args with output JSON parsing."""
    tools_dir = str(tmp_path)
    binary_path = tmp_path / "valid_tool"

    script = (
        "#!/usr/bin/env python3\n"
        "import sys, json\n"
        "args = {}\n"
        "if '--json-args' in sys.argv:\n"
        "    idx = sys.argv.index('--json-args')\n"
        "    args = json.loads(sys.argv[idx + 1])\n"
        "print(json.dumps({'status': 'ok', 'processed': args}))\n"
    )
    binary_path.write_text(script)
    binary_path.chmod(0o755)

    dispatcher = LocalToolDispatcher(tools_dir=tools_dir)
    user_ctx = DataPlaneUserContext(user_id="usr_test", role="developer")

    res = await dispatcher.dispatch_tool_call(
        "valid_tool", {"param1": "hello"}, user_context=user_ctx
    )

    assert res["jsonrpc"] == "2.0"
    assert "result" in res
    assert res["result"]["status"] == "SUCCESS"
    assert res["result"]["output"]["status"] == "ok"
    assert res["result"]["output"]["processed"] == {"param1": "hello"}


@pytest.mark.asyncio
@pytest.mark.unit
async def test_subprocess_timeout_mapping(tmp_path):
    """Verify subprocess timing out maps to -32603 Internal Error."""
    tools_dir = str(tmp_path)
    slow_binary = tmp_path / "slow_tool"

    script = "#!/usr/bin/env python3\nimport time\ntime.sleep(5.0)\n"
    slow_binary.write_text(script)
    slow_binary.chmod(0o755)

    dispatcher = LocalToolDispatcher(tools_dir=tools_dir, timeout_seconds=0.1)
    res = await dispatcher.dispatch_tool_call("slow_tool", {})

    assert res["jsonrpc"] == "2.0"
    assert "error" in res
    assert res["error"]["code"] == -32603
    assert "timed out" in res["error"]["message"].lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_subprocess_non_zero_exit_status(tmp_path):
    """Verify non-zero process returncode maps to result status ERROR or -32603 error."""
    tools_dir = str(tmp_path)
    failing_binary = tmp_path / "failing_tool"

    script = "#!/usr/bin/env python3\nimport sys\nsys.stderr.write('fatal crash\\n')\nsys.exit(1)\n"
    failing_binary.write_text(script)
    failing_binary.chmod(0o755)

    dispatcher = LocalToolDispatcher(tools_dir=tools_dir)
    res = await dispatcher.dispatch_tool_call("failing_tool", {})

    assert res["jsonrpc"] == "2.0"
    if "result" in res:
        assert res["result"]["status"] == "ERROR"
        assert "fatal crash" in res["result"]["stderr"]
    else:
        assert res["error"]["code"] == -32603


@pytest.mark.asyncio
@pytest.mark.unit
async def test_catalog_reading_and_search_tools(tmp_path):
    """Verify read_catalog reads catalog.json and mcp__search_tools filters entries."""
    tools_dir = str(tmp_path)
    catalog_path = tmp_path / "catalog.json"

    fake_catalog = {
        "tools": [
            {"name": "arm_v9_sme", "description": "SME2 vector acceleration"},
            {"name": "ros2_filter", "description": "ROS2 PointCloud2 filter"},
        ]
    }
    catalog_path.write_text(json.dumps(fake_catalog))

    dispatcher = LocalToolDispatcher(tools_dir=tools_dir)

    tools = await dispatcher.read_catalog()
    assert any(t["name"] == "arm_v9_sme" for t in tools)
    assert any(t["name"] == "ros2_filter" for t in tools)

    search_res = await dispatcher.dispatch_tool_call("mcp__search_tools", {"query": "SME"})
    assert search_res["jsonrpc"] == "2.0"
    assert search_res["result"]["status"] == "SUCCESS"
    assert len(search_res["result"]["matches"]) == 1
    assert search_res["result"]["matches"][0]["name"] == "arm_v9_sme"
