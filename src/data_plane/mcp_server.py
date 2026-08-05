"""Standalone FastMCP Server & JSON-RPC 2.0 Data Plane Endpoint.

Exposes `/api/v1/mcp` HTTP/2 JSON-RPC endpoint with isolated zero-trust identity propagation,
MCP 2026-07-28 header negotiation, and LocalToolDispatcher tool execution routing.
"""

import json
import logging
from contextvars import ContextVar
from typing import Any

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from fastmcp import FastMCP

from src.data_plane.schemas import (
    DataPlaneJSONRPCError,
    DataPlaneJSONRPCRequest,
    DataPlaneJSONRPCResponse,
    DataPlaneUserContext,
    ServerDiscoverResult,
)
from src.data_plane.worker import LocalToolDispatcher

logger = logging.getLogger("mvcp.data_plane_mcp_server")

# Task-isolated context variable for downstream identity propagation
user_context_var: ContextVar[DataPlaneUserContext | None] = ContextVar(
    "user_context_var", default=None
)


def get_current_user_context() -> DataPlaneUserContext | None:
    """Returns the DataPlaneUserContext for the active task execution context."""
    return user_context_var.get()


# FastMCP instance serves as the registration handle for FastMCP decorators and SDK
# bridging in Phase 2.2, while the /api/v1/mcp endpoint directly delegates tool
# execution requests to the module-level LocalToolDispatcher singleton.
mcp = FastMCP("data-plane-mcp")

# Module-level LocalToolDispatcher singleton to avoid catalog reloading overhead per request
dispatcher = LocalToolDispatcher()

# Initialize ASGI FastAPI Application
app = FastAPI(
    title="Data Plane FastMCP Server",
    description="gVisor Sandboxed FastMCP Execution Engine",
    version="0.1.0",
)


@app.middleware("http")
async def extract_identity_context_middleware(request: Request, call_next: Any) -> Response:
    """Middleware extracting downstream identity headers into a task-isolated ContextVar.

    Enforces zero-trust upstream authentication by verifying the presence of X-User-ID.
    Uses a try...finally block with token.reset() to prevent cross-request context bleeding.
    """
    user_id = request.headers.get("X-User-ID")

    if not user_id:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Missing upstream identity header: X-User-ID"},
        )

    role = request.headers.get("X-User-Role", "user")
    raw_scopes = request.headers.get("X-User-Scopes", "")
    scopes = [s.strip() for s in raw_scopes.split(",") if s.strip()]
    protocol_version = request.headers.get("MCP-Protocol-Version", "2026-07-28")

    ctx = DataPlaneUserContext(
        user_id=user_id,
        role=role,
        scopes=scopes,
        protocol_version=protocol_version,
    )
    token = user_context_var.set(ctx)

    try:
        response = await call_next(request)
        return response
    finally:
        user_context_var.reset(token)


@app.post("/api/v1/mcp", response_model=DataPlaneJSONRPCResponse)
async def handle_mcp_jsonrpc_endpoint(request: Request) -> JSONResponse:
    """Handles incoming JSON-RPC 2.0 MCP requests over HTTP/2.

    Supported methods:
    - 'server/discover': Stateless MCP 2026-07-28 capabilities and version discovery.
    - 'initialize': Legacy fallback for MCP discovery.
    - 'tools/list': Returns catalog of available tools.
    - 'tools/call': Executes tool via LocalToolDispatcher.
    """
    try:
        raw_body = await request.body()
        if not raw_body:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=DataPlaneJSONRPCResponse(
                    jsonrpc="2.0",
                    id=None,
                    error=DataPlaneJSONRPCError(code=-32700, message="Parse error: Empty body"),
                ).model_dump(exclude_none=True),
            )
        body = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=DataPlaneJSONRPCResponse(
                jsonrpc="2.0",
                id=None,
                error=DataPlaneJSONRPCError(
                    code=-32700, message=f"Parse error: Invalid JSON payload ({str(e)})"
                ),
            ).model_dump(exclude_none=True),
        )

    if isinstance(body, list):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=DataPlaneJSONRPCResponse(
                jsonrpc="2.0",
                id=None,
                error=DataPlaneJSONRPCError(
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
            content=DataPlaneJSONRPCResponse(
                jsonrpc="2.0",
                id=None,
                error=DataPlaneJSONRPCError(
                    code=-32600, message="Invalid Request: JSON payload must be an object"
                ),
            ).model_dump(exclude_none=True),
        )

    req_id = body.get("id")

    try:
        rpc_request = DataPlaneJSONRPCRequest.model_validate(body)
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=DataPlaneJSONRPCResponse(
                jsonrpc="2.0",
                id=req_id,
                error=DataPlaneJSONRPCError(
                    code=-32600, message=f"Invalid Request schema: {str(e)}"
                ),
            ).model_dump(exclude_none=True),
        )

    try:
        if rpc_request.method in ("server/discover", "initialize"):
            discover_result = ServerDiscoverResult().model_dump(by_alias=True)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=DataPlaneJSONRPCResponse(
                    jsonrpc="2.0", id=rpc_request.id, result=discover_result
                ).model_dump(exclude_none=True),
            )

        elif rpc_request.method == "tools/list":
            tools_list = await dispatcher._read_catalog()
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=DataPlaneJSONRPCResponse(
                    jsonrpc="2.0", id=rpc_request.id, result={"tools": tools_list}
                ).model_dump(exclude_none=True),
            )

        elif rpc_request.method == "tools/call":
            params = rpc_request.params or {}
            tool_name = params.get("name") or params.get("tool_name")
            arguments = params.get("arguments") or {}

            if not tool_name:
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content=DataPlaneJSONRPCResponse(
                        jsonrpc="2.0",
                        id=rpc_request.id,
                        error=DataPlaneJSONRPCError(
                            code=-32602,
                            message="Invalid Params: Tool name parameter required for tools/call",
                        ),
                    ).model_dump(exclude_none=True),
                )

            dispatch_res = await dispatcher.dispatch_tool_call(tool_name, arguments)

            # Check if LocalToolDispatcher returned an internal error structure
            if isinstance(dispatch_res, dict) and "error" in dispatch_res:
                err_dict = dispatch_res["error"]
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content=DataPlaneJSONRPCResponse(
                        jsonrpc="2.0",
                        id=rpc_request.id,
                        error=DataPlaneJSONRPCError(
                            code=err_dict.get("code", -32603),
                            message=err_dict.get("message", "Tool execution error"),
                            data=err_dict.get("data"),
                        ),
                    ).model_dump(exclude_none=True),
                )

            res_payload = (
                dispatch_res.get("result", dispatch_res)
                if isinstance(dispatch_res, dict)
                else dispatch_res
            )

            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=DataPlaneJSONRPCResponse(
                    jsonrpc="2.0", id=rpc_request.id, result=res_payload
                ).model_dump(exclude_none=True),
            )

        elif rpc_request.method.startswith("notifications/"):
            # Notifications execution completes without requiring a result body
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=DataPlaneJSONRPCResponse(
                    jsonrpc="2.0", id=None, result={"status": "acknowledged"}
                ).model_dump(exclude_none=True),
            )

        else:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=DataPlaneJSONRPCResponse(
                    jsonrpc="2.0",
                    id=rpc_request.id,
                    error=DataPlaneJSONRPCError(
                        code=-32601, message=f"Method '{rpc_request.method}' not found"
                    ),
                ).model_dump(exclude_none=True),
            )

    except Exception as e:
        logger.error(f"[mcp_server] Error executing method '{rpc_request.method}': {e}")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=DataPlaneJSONRPCResponse(
                jsonrpc="2.0",
                id=rpc_request.id,
                error=DataPlaneJSONRPCError(
                    code=-32603, message=f"Internal execution error: {str(e)}"
                ),
            ).model_dump(exclude_none=True),
        )


__all__ = [
    "app",
    "mcp",
    "dispatcher",
    "user_context_var",
    "get_current_user_context",
]
