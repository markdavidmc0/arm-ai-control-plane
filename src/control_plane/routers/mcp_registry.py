"""MCP Registry & Multiplexer APIRouter.

Provides Workspace Slicing endpoints (`/api/v1/registry/tools`) inspecting
`X-Workspace-Context` header (< 1,500 tokens), search meta-tool execution,
dynamic tool registration (`/api/v1/registry/register`), upstream MCP server registration
(`/api/v1/registry/servers/register`), and transparent federated tool execution (`/api/v1/registry/call`).
"""

from typing import Any
from fastapi import APIRouter, Header
from pydantic import BaseModel, Field
from src.control_plane.services.mcp_multiplexer import MCPMultiplexerService
from src.control_plane.services.upstream_mcp_client import UpstreamMCPClientService

router = APIRouter(prefix="/api/v1/registry", tags=["MCP Master Registry"])
multiplexer_service = MCPMultiplexerService()
upstream_client_service = UpstreamMCPClientService()


class RegisterToolRequest(BaseModel):
    domain: str = Field(
        ..., json_schema_extra={"example": "physical-ai"}, description="Workspace domain category"
    )
    tool_schema: dict[str, Any] = Field(..., description="Valid MCP tool schema object")


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
async def register_domain_tool(req: RegisterToolRequest):
    """Registers a new tool dynamically into the Master MCP Registry from CI/CD workflows."""
    res = multiplexer_service.register_tool(domain=req.domain, tool_schema=req.tool_schema)
    return res


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
        # Reverse proxy tool execution frame down to upstream server URL
        result = await upstream_client_service.proxy_tool_call(
            endpoint_url=endpoint_url, tool_name=req.name, arguments=req.arguments
        )
        return result
    else:
        # Local execution response
        return {
            "jsonrpc": "2.0",
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": f"Executed tool [{req.name}] locally on Arm Control Plane Gateway.",
                    }
                ],
                "status": "SUCCESS",
            },
        }
