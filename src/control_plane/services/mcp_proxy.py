"""Control Plane MCP Proxy Service for Data Plane Tool Dispatch."""

import uuid
from typing import Any

import httpx

from src.control_plane.schemas import UserContext


class MCPProxyService:
    """Async HTTP/2 proxy forwarding tool execution calls with identity propagation."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        """Initializes the MCPProxyService with an injected HTTP client.

        Args:
            client: Pre-configured httpx.AsyncClient instance with target base_url.
        """
        self.client = client

    async def forward_request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        user_context: UserContext | None = None,
        request_id: Any | None = None,
        path: str = "/api/v1/mcp",
    ) -> dict[str, Any]:
        """Forwards a JSON-RPC 2.0 request payload to the Data Plane via relative URL path.

        Args:
            method: Target JSON-RPC method name (e.g. 'tools/call', 'tools/list').
            params: Method parameter mapping.
            user_context: Active UserContext for zero-trust identity propagation.
            request_id: Optional custom request identifier.
            path: Relative endpoint path on the Data Plane. Defaults to '/api/v1/mcp'.

        Returns:
            JSON-RPC 2.0 response dictionary from the Data Plane.
        """
        req_id = request_id or f"proxy-{uuid.uuid4().hex[:8]}"
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        }

        headers = {"Content-Type": "application/json"}
        if user_context:
            headers["X-User-ID"] = user_context.user_id
            headers["X-User-Role"] = user_context.role
            headers["X-User-Scopes"] = ", ".join(user_context.scopes)

        try:
            response = await self.client.post(path, json=payload, headers=headers)
            if response.status_code != 200:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32603,
                        "message": (
                            f"Data Plane MCP HTTP error {response.status_code}: {response.text}"
                        ),
                    },
                }
            return response.json()
        except httpx.TimeoutException as err:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32000,
                    "message": f"Data Plane MCP request timed out: {str(err)}",
                },
            }
        except httpx.HTTPError as err:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32603,
                    "message": f"Data Plane MCP proxy execution error: {str(err)}",
                },
            }
        except Exception as err:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32603,
                    "message": f"Unexpected MCP proxy error: {str(err)}",
                },
            }

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        user_context: UserContext | None = None,
    ) -> dict[str, Any]:
        """Forwards a FastMCP tool call request to the Data Plane engine over HTTP/2.

        Args:
            name: Identifier of the FastMCP tool to invoke.
            arguments: Parameter dictionary for the tool invocation.
            user_context: Active UserContext for zero-trust identity propagation.

        Returns:
            JSON-RPC 2.0 response dictionary from the Data Plane.
        """
        return await self.forward_request(
            method="tools/call",
            params={
                "name": name,
                "arguments": arguments or {},
            },
            user_context=user_context,
        )

    async def close(self) -> None:
        """Closes the underlying HTTP client if not already closed."""
        if not self.client.is_closed:
            await self.client.aclose()
