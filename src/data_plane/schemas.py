"""Data Plane Isolated Request and Response Pydantic Schemas & Type Definitions.

These models maintain complete schema isolation from Control Plane modules.
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
]


class DataPlaneUserContext(BaseModel):
    """User identity context parsed from pre-authenticated downstream HTTP headers."""

    model_config = ConfigDict(extra="ignore")

    user_id: str = Field(..., description="Unique user identifier from downstream identity header")
    role: str = Field("user", description="Assigned authorization role")
    scopes: list[str] = Field(default_factory=list, description="List of granted permission scopes")


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

    model_config = ConfigDict(extra="ignore")

    jsonrpc: Literal["2.0"] = Field("2.0", description="JSON-RPC protocol version")
    id: str | int | None = Field(
        None, description="Optional request identifier (None for notifications)"
    )
    method: str = Field(
        ..., description="Target JSON-RPC method name (e.g., 'tools/call', 'tools/list')"
    )
    params: dict[str, Any] = Field(default_factory=dict, description="Method parameter dictionary")


class DataPlaneJSONRPCResponse(BaseModel):
    """Pydantic schema for outgoing MCP JSON-RPC 2.0 responses from the Data Plane."""

    model_config = ConfigDict(extra="ignore")

    jsonrpc: Literal["2.0"] = Field("2.0", description="JSON-RPC protocol version")
    id: str | int | None = Field(..., description="Corresponding request identifier")
    result: Any | None = Field(None, description="Successful execution payload")
    error: DataPlaneJSONRPCError | None = Field(
        None, description="Structured error payload if request execution failed"
    )
