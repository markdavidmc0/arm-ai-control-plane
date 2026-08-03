"""MCP Registry & Multiplexer APIRouter.

Provides Workspace Slicing endpoints (`/api/v1/registry/tools`), search meta-tool execution,
domain-sliced tool registration (`/api/v1/registry/register`), upstream MCP server registration
(`/api/v1/registry/servers/register`), and transparent federated tool execution (`/api/v1/registry/call`).
"""

from typing import Any
from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field
from src.control_plane.services.auth_service import AuthService
from src.control_plane.services.mcp_multiplexer import MCPMultiplexerService
from src.control_plane.services.upstream_mcp_client import UpstreamMCPClientService

router = APIRouter(prefix="/api/v1/registry", tags=["MCP Master Registry"])
multiplexer_service = MCPMultiplexerService()
upstream_client_service = UpstreamMCPClientService()
auth_service = AuthService()


class RegisterToolRequest(BaseModel):
    domain: str | None = Field(
        None, json_schema_extra={"example": "physical-ai"}, description="Workspace domain category"
    )
    tool_schema: dict[str, Any] | None = Field(None, description="Valid MCP tool schema object")
    tools: list[dict[str, Any]] | None = Field(None, description="Batch list of domain-sliced tool schemas")


class SearchToolsRequest(BaseModel):
    query: str = Field(
        ..., json_schema_extra={"example": "vectorization"}, description="Keywords to search"
    )
    domain: str | None = Field(
        None, json_schema_extra={"example": "physical-ai"}, description="Optional domain filter"
    )


class RegisterServerRequest(BaseModel):
    server_id: str = Field(
        ..., json_schema_extra={"example": "official-arm-mcp"}, description="Unique server ID"
    )
    domain: str = Field(
        "base", json_schema_extra={"example": "base"}, description="Domain category or 'base'"
    )
    endpoint_url: str = Field(
        ...,
        json_schema_extra={"example": "http://official-arm-mcp.internal:8000/mcp"},
        description="Server URL",
    )


class ToolCallRequest(BaseModel):
    name: str = Field(..., description="Tool name to execute")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool execution arguments")


@router.get("/tools")
async def list_sliced_tools(
    x_workspace_context: str | None = Header(None, alias="x-workspace-context"),
):
    """Returns context-sliced MCP tool list for active workspace domain (< 1,500 tokens)."""
    tools = multiplexer_service.get_sliced_tools(workspace_context=x_workspace_context)

    json_str = str(tools)
    estimated_tokens = len(json_str) // 4

    return {
        "workspace_context": x_workspace_context or "default_foundations",
        "tool_count": len(tools),
        "estimated_token_footprint": estimated_tokens,
        "tools": tools,
    }


@router.post("/search")
async def search_tools_meta(req: SearchToolsRequest):
    """Lazy-loaded mcp__search_tools meta-tool handler for on-demand tool schema discovery."""
    matches = multiplexer_service.search_tools(query=req.query, domain=req.domain)
    return {
        "query": req.query,
        "domain_filter": req.domain,
        "match_count": len(matches),
        "matches": matches,
    }


@router.post("/register")
async def register_domain_tool(
    req: RegisterToolRequest,
    x_judge_api_key: str | None = Header(None, alias="x-judge-api-key"),
    authorization: str | None = Header(None, alias="authorization"),
):
    """Registers new tools dynamically into the Master MCP Registry via Keycloak JWT or API Key.

    Supports both single tool registration (`tool_schema`) and domain-sliced batch registration (`tools`).
    """
    key_to_check = authorization or x_judge_api_key
    if key_to_check:
        record = auth_service.verify_key(key_to_check)
        if not record:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired Keycloak JWT Bearer Token or API Key.",
            )

    registered_tools = []

    # Handle Batch Tools Array Payload
    if req.tools:
        for tool in req.tools:
            target_domain = tool.get("domain") or req.domain or "cloud-ai"
            res = multiplexer_service.register_tool(domain=target_domain, tool_schema=tool)
            registered_tools.append(res)
        return {
            "status": "SUCCESS",
            "message": f"Registered {len(registered_tools)} domain-sliced tools.",
            "registered_count": len(registered_tools),
            "tools": registered_tools,
        }

    # Handle Single Tool Payload
    if req.tool_schema and req.domain:
        res = multiplexer_service.register_tool(domain=req.domain, tool_schema=req.tool_schema)
        return res

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Payload must contain either 'tools' array or 'tool_schema' object with 'domain'.",
    )


@router.post("/servers/register")
async def register_upstream_server(req: RegisterServerRequest):
    """Registers an upstream MCP server, performs `tools/list` handshake, and auto-persists schemas."""
    tools = await upstream_client_service.handshake_tools(endpoint_url=req.endpoint_url)
    res = multiplexer_service.register_server(
        server_id=req.server_id, domain=req.domain, endpoint_url=req.endpoint_url, tools=tools
    )
    return res


@router.get("/servers")
async def list_upstream_servers():
    """Lists all registered upstream/official MCP servers."""
    return {
        "server_count": len(multiplexer_service.upstream_servers),
        "servers": multiplexer_service.upstream_servers,
    }


@router.post("/call")
async def execute_tool_call(req: ToolCallRequest):
    """Unified federated tool execution endpoint. Routes tool call locally or proxies to upstream server."""
    is_upstream, endpoint_url = multiplexer_service.get_tool_owner(req.name)

    if is_upstream and endpoint_url:
        result = await upstream_client_service.proxy_tool_call(
            endpoint_url=endpoint_url, tool_name=req.name, arguments=req.arguments
        )
        return result
    else:
        # Route local tool call to Data Plane Subprocess Dispatcher
        from src.data_plane.worker.tool_dispatcher import LocalToolDispatcher
        dispatcher = LocalToolDispatcher()
        return await dispatcher.dispatch_tool_call(req.name, req.arguments)
