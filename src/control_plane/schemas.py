"""Control Plane API Request and Response Pydantic Schemas & Type Definitions."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "UserContext",
    "JSONRPCError",
    "MCPJsonRPCRequest",
    "MCPJsonRPCResponse",
    "ToolsCallParams",
    "ToolDefinitionSchema",
    "ToolsListResult",
    "ControlPlaneHealthResponse",
    "ToolRegistrationSchema",
]


class JSONRPCError(BaseModel):
    """Standard JSON-RPC 2.0 Error object schema."""

    model_config = ConfigDict(extra="ignore")

    code: int = Field(..., description="JSON-RPC error code (e.g., -32601 Method Not Found)")
    message: str = Field(..., description="Short description of the error")
    data: Any | None = Field(None, description="Optional detailed error context or trace")


class ToolsCallParams(BaseModel):
    """Pydantic schema for parameters passed to 'tools/call' method."""

    model_config = ConfigDict(extra="ignore")

    name: str | None = Field(None, description="Target tool identifier name")
    tool_name: str | None = Field(None, description="Alternative tool identifier alias")
    arguments: dict[str, Any] = Field(
        default_factory=dict, description="Dictionary of argument key-value pairs"
    )


class ToolDefinitionSchema(BaseModel):
    """Pydantic schema describing an available tool in the catalog."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="Unique tool identifier name")
    description: str = Field(..., description="Tool capability description")
    inputSchema: dict[str, Any] = Field(  # noqa: N815
        default_factory=dict, description="JSON Schema defining expected arguments"
    )


class ToolsListResult(BaseModel):
    """Pydantic schema for successful 'tools/list' result payload."""

    model_config = ConfigDict(extra="ignore")

    tools: list[dict[str, Any]] = Field(
        default_factory=list, description="List of registered tool catalog definitions"
    )


class MCPJsonRPCRequest(BaseModel):
    """Pydantic schema for outgoing/incoming MCP JSON-RPC 2.0 requests."""

    model_config = ConfigDict(extra="ignore")

    jsonrpc: Literal["2.0"] = Field("2.0", description="JSON-RPC protocol version")
    id: str | int | None = Field(None, description="Optional request ID (None for notifications)")
    method: str = Field(
        ..., description="Target MCP method name (e.g., 'tools/call', 'tools/list')"
    )
    params: dict[str, Any] = Field(default_factory=dict, description="Method parameters")


class MCPJsonRPCResponse(BaseModel):
    """Pydantic schema for MCP JSON-RPC 2.0 responses."""

    model_config = ConfigDict(extra="ignore")

    jsonrpc: Literal["2.0"] = Field("2.0", description="JSON-RPC protocol version")
    id: str | int | None = Field(..., description="Corresponding request ID")
    result: Any | None = Field(None, description="Successful result payload")
    error: JSONRPCError | None = Field(None, description="Structured JSON-RPC error payload")


class ControlPlaneHealthResponse(BaseModel):
    """Pydantic schema for Control Plane gateway health readiness responses."""

    status: str = Field("healthy", description="Gateway readiness status")
    identity_layer: str = Field(
        "keycloak_wif",
        description="Identity and OIDC Workload Identity Federation provider",
    )


class ToolRegistrationSchema(BaseModel):
    """Pydantic schema for dynamic tool registration requests."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="Unique tool identifier name")
    description: str = Field(..., description="Tool capability description")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Tool parameters input schema"
    )
    entrypoint: str | None = Field(
        None, description="Optional execution binary or script entrypoint"
    )


class UserContext(BaseModel):
    """User context container parsed from pre-authenticated Envoy HTTP headers."""

    user_id: str
    role: str = "user"
    scopes: list[str] = Field(default_factory=list)
