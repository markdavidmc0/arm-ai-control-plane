"""Pure Model Context Protocol (MCP) JSON-RPC 2.0 Protocol Gateway.

Translates standard MCP JSON-RPC 2.0 requests (initialize, notifications/initialized,
tools/list, tools/call, resources/list, resources/read) and delegates tool execution
dynamically to the Data Plane dispatcher and SandboxOrchestrator without domain-specific hardcoding.
"""

import json
import logging
from typing import Any

from fastmcp import FastMCP

logger = logging.getLogger("mvcp.mcp_server")

# Initialize lightweight FastMCP instance for ASGI/WSGI mounting
mcp = FastMCP("arm-mvcp-gateway")


class MCPServer:
    """Model Context Protocol (MCP) JSON-RPC 2.0 Gateway.

    Provides standard protocol handler routing and dynamic tool execution forwarding
    to Data Plane workers and SandboxOrchestrator.
    """

    def __init__(self, orchestrator=None, tool_dispatcher=None):
        """Initializes the MCP Gateway.

        Args:
            orchestrator: An optional Sandbox orchestrator instance.
            tool_dispatcher: An optional LocalToolDispatcher instance.
        """
        from src.control_plane.orchestrator import SandboxOrchestrator
        from src.data_plane.worker.tool_dispatcher import LocalToolDispatcher

        self.orchestrator = orchestrator or SandboxOrchestrator()
        self.dispatcher = tool_dispatcher or LocalToolDispatcher()

    async def handle_mcp_request(self, request_body: dict[str, Any]) -> dict[str, Any]:
        """Processes standard MCP JSON-RPC 2.0 request payloads.

        Args:
            request_body: The raw JSON-RPC dictionary from the client.

        Returns:
            A standard JSON-RPC 2.0 response dictionary containing either results
            or structured error frames.
        """
        method = request_body.get("method")
        req_id = request_body.get("id")
        params = request_body.get("params", {})

        logger.info(f"Received MCP RPC Call: {method} (id={req_id})")

        try:
            if method == "initialize":
                return self._build_jsonrpc_response(
                    req_id,
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}, "resources": {}},
                        "serverInfo": {"name": "mvcp-gke-gateway", "version": "1.0.0"},
                    },
                )
            elif method == "notifications/initialized":
                return self._build_jsonrpc_response(req_id, {})
            elif method == "tools/list":
                tools_result = await self._list_tools()
                return self._build_jsonrpc_response(req_id, tools_result)
            elif method == "tools/call":
                result = await self._call_tool(params)
                return self._build_jsonrpc_response(req_id, result)
            elif method == "resources/list":
                resources_result = await self._list_resources()
                return self._build_jsonrpc_response(req_id, resources_result)
            elif method == "resources/read":
                result = await self._read_resource(params)
                return self._build_jsonrpc_response(req_id, result)
            else:
                return self._build_jsonrpc_error(req_id, -32601, f"Method not found: {method}")
        except Exception as e:
            logger.error(f"Error handling MCP request: {e}")
            return self._build_jsonrpc_error(req_id, -32603, f"Internal error: {str(e)}")

    async def _list_tools(self) -> dict[str, Any]:
        """Dynamically fetches available tool definitions from the Data Plane catalog."""
        catalog_tools = await self.dispatcher._read_catalog()
        tools_schema = []
        for tool in catalog_tools:
            tools_schema.append(
                {
                    "name": tool.get("name"),
                    "description": tool.get("description", ""),
                    "inputSchema": tool.get("inputSchema", {"type": "object", "properties": {}}),
                }
            )
        return {"tools": tools_schema}

    async def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        """Delegates tool call payload execution directly to Orchestrator or Data Plane Dispatcher."""
        import uuid

        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if not tool_name:
            raise ValueError("Missing 'name' in tools/call parameters.")

        # If GKE/Kind cluster orchestrator is configured, delegate kernel optimization directly
        if self.orchestrator.k8s_client_configured and tool_name in [
            "optimize_kernel",
            "profile_and_optimize_kernel",
        ]:
            code = arguments.get("code") or arguments.get("source_code", "")
            task_id = str(uuid.uuid4())
            profile_res = await self.orchestrator.optimize_and_profile(task_id, code)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(profile_res)
                        if isinstance(profile_res, dict)
                        else str(profile_res),
                    }
                ]
            }

        # Otherwise, delegate directly to the Data Plane tool dispatcher
        dispatch_res = await self.dispatcher.dispatch_tool_call(tool_name, arguments)
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(dispatch_res)
                    if isinstance(dispatch_res, dict)
                    else str(dispatch_res),
                }
            ]
        }

    async def _list_resources(self) -> dict[str, Any]:
        """Declares dynamic resources."""
        return {"resources": []}

    async def _read_resource(self, params: dict[str, Any]) -> dict[str, Any]:
        """Retrieves dynamic resources."""
        uri = params.get("uri")
        raise ValueError(f"Resource not found: {uri}")

    def _build_jsonrpc_response(self, req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        """Constructs a standard JSON-RPC 2.0 success frame."""
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def _build_jsonrpc_error(self, req_id: Any, code: int, message: str) -> dict[str, Any]:
        """Constructs a standard JSON-RPC 2.0 error frame."""
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        }


if __name__ == "__main__":
    mcp.run()
