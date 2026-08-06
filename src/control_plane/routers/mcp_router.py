"""Unified Control Plane MCP Gateway Router.

Exposes `/api/v1/mcp` JSON-RPC 2.0 gateway endpoint delegating tool discovery
(`tools/list`) and execution (`tools/call`) to the Data Plane over HTTP/2 boundary.
"""

import json
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from src.control_plane.dependencies import (
    get_data_plane_client,
    get_user_context,
)
from src.control_plane.schemas import (
    JSONRPCError,
    MCPJsonRPCRequest,
    MCPJsonRPCResponse,
    UserContext,
)

logger = logging.getLogger("mvcp.routers.mcp_router")

router = APIRouter(prefix="/mcp", tags=["MCP Gateway Router"])


@router.post("", response_model=MCPJsonRPCResponse)
async def handle_mcp_gateway_endpoint(
    request: Request,
    user_context: UserContext = Depends(get_user_context),
    data_plane_client: httpx.AsyncClient = Depends(get_data_plane_client),
) -> JSONResponse:
    """Handles incoming MCP JSON-RPC 2.0 gateway requests over HTTP/2.

    Supported methods:
    - 'tools/list': Proxies tool catalog discovery request to Data Plane.
    - 'tools/call': Proxies target tool execution payload to Data Plane.

    Args:
        request: FastAPI Request instance containing raw request body.
        user_context: Authenticated UserContext extracted from HTTP headers.
        data_plane_client: Injected httpx.AsyncClient targeting Data Plane base URL.

    Returns:
        JSONResponse wrapping MCPJsonRPCResponse payload from Data Plane.
    """
    try:
        raw_body = await request.body()
        if not raw_body:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=MCPJsonRPCResponse(
                    jsonrpc="2.0",
                    id=None,
                    error=JSONRPCError(code=-32700, message="Parse error: Empty body"),
                ).model_dump(exclude_none=True),
            )
        body = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=MCPJsonRPCResponse(
                jsonrpc="2.0",
                id=None,
                error=JSONRPCError(
                    code=-32700, message=f"Parse error: Invalid JSON payload ({str(e)})"
                ),
            ).model_dump(exclude_none=True),
        )

    if isinstance(body, list):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=MCPJsonRPCResponse(
                jsonrpc="2.0",
                id=None,
                error=JSONRPCError(
                    code=-32600,
                    message=(
                        "Invalid Request: Batch JSON-RPC requests are not supported. "
                        "Payload must be a single JSON object."
                    ),
                ),
            ).model_dump(exclude_none=True),
        )

    if not isinstance(body, dict):
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=MCPJsonRPCResponse(
                jsonrpc="2.0",
                id=None,
                error=JSONRPCError(
                    code=-32600, message="Invalid Request: JSON payload must be an object"
                ),
            ).model_dump(exclude_none=True),
        )

    req_id: Any = body.get("id")

    try:
        rpc_request = MCPJsonRPCRequest.model_validate(body)
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=MCPJsonRPCResponse(
                jsonrpc="2.0",
                id=req_id,
                error=JSONRPCError(code=-32600, message=f"Invalid Request schema: {str(e)}"),
            ).model_dump(exclude_none=True),
        )

    # Forward identity claims downstream to the Data Plane via HTTP headers
    forwarded_headers = {
        "X-User-ID": user_context.user_id,
        "X-User-Role": user_context.role,
        "X-User-Scopes": ",".join(user_context.scopes),
    }

    try:
        response = await data_plane_client.post(
            "/api/v1/mcp",
            json=rpc_request.model_dump(exclude_none=True),
            headers=forwarded_headers,
        )
        return JSONResponse(
            status_code=response.status_code,
            content=response.json(),
        )
    except httpx.HTTPStatusError as e:
        logger.error(
            f"[mcp_router] Data Plane returned HTTP error {e.response.status_code}: {e.response.text}"
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=MCPJsonRPCResponse(
                jsonrpc="2.0",
                id=rpc_request.id,
                error=JSONRPCError(
                    code=-32603,
                    message=f"Data Plane execution HTTP error: {e.response.text}",
                ),
            ).model_dump(exclude_none=True),
        )
    except Exception as e:
        logger.error(
            f"[mcp_router] Error communicating with Data Plane for method '{rpc_request.method}': {e}",
            exc_info=True,
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=MCPJsonRPCResponse(
                jsonrpc="2.0",
                id=rpc_request.id,
                error=JSONRPCError(
                    code=-32603,
                    message=f"Data Plane service unavailable or execution failed: {str(e)}",
                ),
            ).model_dump(exclude_none=True),
        )


__all__ = ["router", "handle_mcp_gateway_endpoint"]
