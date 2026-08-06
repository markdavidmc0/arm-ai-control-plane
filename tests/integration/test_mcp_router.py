"""Integration tests for Unified Control Plane MCP Gateway Router at /api/v1/mcp.

Verifies tools/list catalog discovery, tools/call SFI execution,
script entrypoint invocation, and invalid method standard error responses (-32601).
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.config import Settings
from src.control_plane.main import app

DEFAULT_HEADERS = {
    "X-User-ID": "usr_mcp_integration_test",
    "X-User-Role": "developer",
    "X-User-Scopes": "tools:execute",
    "MCP-Protocol-Version": "2026-07-28",
}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_mcp_tools_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Issues JSON-RPC tools/list to /api/v1/mcp and asserts built-in and dynamic catalog tools."""
    # Set isolated ARM_TOOLS_DIR for catalog hot-reload testing
    tools_dir = tmp_path / "arm_tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ARM_TOOLS_DIR", str(tools_dir))

    # Write a dynamic tool entry into catalog.json
    catalog_path = tools_dir / "catalog.json"
    catalog_data = {
        "tools": [
            {
                "name": "dynamic_test_tool",
                "description": "Dynamic catalog test tool",
                "inputSchema": {"type": "object", "properties": {}},
            }
        ]
    }
    catalog_path.write_text(json.dumps(catalog_data), encoding="utf-8")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://controlplane.test",
        headers=DEFAULT_HEADERS,
    ) as client:
        payload = {
            "jsonrpc": "2.0",
            "id": "list-1",
            "method": "tools/list",
            "params": {},
        }

        # 1. Test when ENABLE_CODE_MODE=True
        mock_settings_true = Settings(ENABLE_CODE_MODE=True)
        with patch("src.data_plane.worker.get_settings", return_value=mock_settings_true):
            response = await client.post("/api/v1/mcp", json=payload)
            assert response.status_code == 200
            data = response.json()
            tool_names = [t["name"] for t in data["result"]["tools"]]
            assert "repl_execute" in tool_names
            assert "execute_code" not in tool_names
            assert "dynamic_test_tool" in tool_names

        # 2. Test when ENABLE_CODE_MODE=False
        mock_settings_false = Settings(ENABLE_CODE_MODE=False)
        with patch("src.data_plane.worker.get_settings", return_value=mock_settings_false):
            response = await client.post("/api/v1/mcp", json=payload)
            assert response.status_code == 200
            data = response.json()
            tool_names = [t["name"] for t in data["result"]["tools"]]
            assert "execute_code" in tool_names
            assert "repl_execute" not in tool_names
            assert "dynamic_test_tool" in tool_names


@pytest.mark.asyncio
@pytest.mark.integration
async def test_mcp_tools_call_sfi() -> None:
    """Issues JSON-RPC tools/call for execute_code / repl_execute and verifies SFI execution."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://controlplane.test",
        headers=DEFAULT_HEADERS,
    ) as client:
        # Test execute_code under ENABLE_CODE_MODE=False
        mock_settings_false = Settings(ENABLE_CODE_MODE=False)
        with patch("src.data_plane.worker.settings", mock_settings_false):
            payload = {
                "jsonrpc": "2.0",
                "id": "call-sfi-1",
                "method": "tools/call",
                "params": {
                    "name": "execute_code",
                    "arguments": {"code": "21 * 2"},
                },
            }

            response = await client.post("/api/v1/mcp", json=payload)
            assert response.status_code == 200
            data = response.json()

            assert data.get("jsonrpc") == "2.0"
            assert data.get("id") == "call-sfi-1"
            assert "result" in data
            res = data["result"]
            assert res.get("status") == "SUCCESS"
            assert res.get("result") == 42


@pytest.mark.asyncio
@pytest.mark.integration
async def test_mcp_tools_call_script_entrypoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Registers a .py tool script in catalog.json and verifies execution over /api/v1/mcp."""
    tools_dir = tmp_path / "arm_tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ARM_TOOLS_DIR", str(tools_dir))

    # Create a simple executable Python script entrypoint
    script_path = tools_dir / "custom_echo.py"
    script_content = (
        "import sys, json, argparse\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--json-args', type=str, default='{}')\n"
        "args = parser.parse_args()\n"
        "payload = json.loads(args.json_args)\n"
        "name = payload.get('name', 'world')\n"
        "print(json.dumps({'message': f'Hello {name}'}))\n"
    )
    script_path.write_text(script_content, encoding="utf-8")

    # Register in catalog.json
    catalog_path = tools_dir / "catalog.json"
    catalog_data = {
        "tools": [
            {
                "name": "custom_echo_tool",
                "description": "Script entrypoint echo tool",
                "entrypoint": "custom_echo.py",
                "inputSchema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                },
            }
        ]
    }
    catalog_path.write_text(json.dumps(catalog_data), encoding="utf-8")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://controlplane.test",
        headers=DEFAULT_HEADERS,
    ) as client:
        payload = {
            "jsonrpc": "2.0",
            "id": "script-1",
            "method": "tools/call",
            "params": {
                "name": "custom_echo_tool",
                "arguments": {"name": "Arm Developer"},
            },
        }

        response = await client.post("/api/v1/mcp", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert data.get("jsonrpc") == "2.0"
        assert data.get("id") == "script-1"
        assert "result" in data
        res = data["result"]
        assert res.get("status") == "SUCCESS"
        assert res.get("output") == {"message": "Hello Arm Developer"}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_mcp_invalid_method() -> None:
    """Verifies unknown JSON-RPC methods return standard error code -32601."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://controlplane.test",
        headers=DEFAULT_HEADERS,
    ) as client:
        payload = {
            "jsonrpc": "2.0",
            "id": "invalid-1",
            "method": "nonexistent/method",
            "params": {},
        }

        response = await client.post("/api/v1/mcp", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert data.get("jsonrpc") == "2.0"
        assert data.get("id") == "invalid-1"
        assert "error" in data
        assert data["error"]["code"] == -32601
        assert "not found" in data["error"]["message"].lower()
