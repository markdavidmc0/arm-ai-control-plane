"""Data Plane Isolated Request and Response Pydantic Schemas & Type Definitions.

These models maintain complete schema isolation from Control Plane modules and align
with the MCP 2026-07-28 protocol specification.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "DataPlaneUserContext",
    "DataPlaneToolRequest",
    "DataPlaneToolResponse",
    "DataPlaneJSONRPCError",
    "DataPlaneJSONRPCRequest",
    "DataPlaneJSONRPCResponse",
    "ServerCapabilities",
    "ServerDiscoverResult",
]


class MCPToolSchema(BaseModel):
    name: str
    description: str
    inputSchema: dict[str, Any]  # noqa: N815


EXECUTE_CODE_TOOL_SCHEMA = MCPToolSchema(
    name="execute_code",
    description="Executes sandboxed Python code within the SFI MontyEngine.",
    inputSchema={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code snippet to execute.",
            },
            "inputs": {
                "type": "object",
                "description": "Optional input variable bindings mapping.",
            },
        },
        "required": ["code"],
    },
).model_dump(by_alias=True)

REPL_EXECUTE_TOOL_SCHEMA = MCPToolSchema(
    name="repl_execute",
    description="Executes stateful sandboxed Python code in REPL mode.",
    inputSchema={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python REPL code snippet to execute.",
            }
        },
        "required": ["code"],
    },
).model_dump(by_alias=True)


class DataPlaneHealthResponse(BaseModel):
    """Pydantic schema for Data Plane execution engine health readiness responses."""

    status: str = Field("healthy", description="Execution worker readiness status")
    service: str = Field("data-plane", description="Microservice component identifier")
    engine: str = Field("gvisor_monty", description="Sandboxed execution engine provider")


class DataPlaneUserContext(BaseModel):
    """User identity context parsed from pre-authenticated downstream HTTP headers."""

    model_config = ConfigDict(extra="ignore")

    user_id: str = Field(..., description="Unique user identifier from downstream identity header")
    role: str = Field("user", description="Assigned authorization role")
    scopes: list[str] = Field(default_factory=list, description="List of granted permission scopes")
    protocol_version: str = Field("2026-07-28", description="Negotiated MCP protocol version")


class DataPlaneToolRequest(BaseModel):
    """Request payload for executing a tool in the Data Plane sandbox."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="Target tool identifier or function name")
    arguments: dict[str, Any] = Field(
        default_factory=dict, description="Keyword arguments passed to tool function"
    )


class DataPlaneToolResponse(BaseModel):
    """Execution response model returned by Data Plane tool dispatchers."""

    model_config = ConfigDict(extra="ignore")

    tool_name: str = Field(..., description="Executed tool name")
    status: str = Field("SUCCESS", description="Execution status ('SUCCESS' or 'ERROR')")
    execution_time_ms: float = Field(0.0, description="Tool execution duration in milliseconds")
    content: list[dict[str, Any]] | None = Field(
        None, description="Formatted content outputs (e.g. text/image blocks)"
    )
    output_data: dict[str, Any] | None = Field(
        None, description="Raw structured data payload produced by the tool"
    )
    error: str | None = Field(None, description="Error detail string if status is 'ERROR'")


class DataPlaneJSONRPCError(BaseModel):
    """Standard JSON-RPC 2.0 Error object schema for Data Plane response payloads."""

    model_config = ConfigDict(extra="ignore")

    code: int = Field(..., description="JSON-RPC 2.0 error code (e.g. -32601 Method Not Found)")
    message: str = Field(..., description="Short explanation of the error")
    data: Any | None = Field(None, description="Optional detailed error context or stack trace")


class DataPlaneJSONRPCRequest(BaseModel):
    """Pydantic schema for incoming MCP JSON-RPC 2.0 requests at the Data Plane boundary."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    jsonrpc: Literal["2.0"] = Field("2.0", description="JSON-RPC protocol version")
    id: str | int | None = Field(
        default=None, description="Optional request identifier (None for notifications)"
    )
    method: str = Field(
        ..., description="Target JSON-RPC method name (e.g., 'tools/call', 'tools/list')"
    )
    params: dict[str, Any] = Field(default_factory=dict, description="Method parameter dictionary")
    meta: dict[str, Any] | None = Field(
        default=None, alias="_meta", description="Optional request metadata"
    )


class DataPlaneJSONRPCResponse(BaseModel):
    """Pydantic schema for outgoing MCP JSON-RPC 2.0 responses from the Data Plane."""

    model_config = ConfigDict(extra="ignore")

    jsonrpc: Literal["2.0"] = Field("2.0", description="JSON-RPC protocol version")
    id: str | int | None = Field(
        default=None, description="Corresponding request identifier (None for notifications)"
    )
    result: Any | None = Field(None, description="Successful execution payload")
    error: DataPlaneJSONRPCError | None = Field(
        None, description="Structured error payload if request execution failed"
    )


class ServerCapabilities(BaseModel):
    """Capabilities supported by the Data Plane FastMCP server (MCP 2026-07-28)."""

    model_config = ConfigDict(extra="ignore")

    tools: dict[str, Any] = Field(default_factory=dict, description="Supported tool capabilities")
    resources: dict[str, Any] = Field(
        default_factory=dict, description="Supported resource capabilities"
    )
    prompts: dict[str, Any] = Field(
        default_factory=dict, description="Supported prompt capabilities"
    )


class ServerDiscoverResult(BaseModel):
    """Response payload for stateless 'server/discover' method (MCP 2026-07-28)."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    protocol_versions: list[str] = Field(
        default_factory=lambda: ["2026-07-28", "2025-11-25"],
        alias="protocolVersions",
        description="Supported MCP protocol versions",
    )
    capabilities: ServerCapabilities = Field(
        default_factory=ServerCapabilities, description="Server capability definitions"
    )
    server_info: dict[str, Any] = Field(
        default_factory=lambda: {"name": "data-plane-mcp", "version": "0.1.0"},
        alias="serverInfo",
        description="Server identity and version metadata",
    )
