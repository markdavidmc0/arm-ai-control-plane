"""Control Plane API Request and Response Pydantic Schemas & Type Definitions."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "UserContext",
    "JSONRPCError",
    "MCPJsonRPCRequest",
    "MCPJsonRPCResponse",
    "HealthStatusResponse",
    "ToolRegistrationSchema",
]


class JSONRPCError(BaseModel):
    """Standard JSON-RPC 2.0 Error object schema."""

    model_config = ConfigDict(extra="ignore")

    code: int = Field(..., description="JSON-RPC error code (e.g., -32601 Method Not Found)")
    message: str = Field(..., description="Short description of the error")
    data: Any | None = Field(None, description="Optional detailed error context or trace")


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


class HealthStatusResponse(BaseModel):
    """Pydantic schema for Control Plane health readiness responses."""

    status: str = Field("healthy", description="Gateway readiness status")
    identity_layer: str = Field(
        "keycloak_wif", description="Identity and OIDC Workload Identity Federation provider"
    )


class ToolRegistrationSchema(BaseModel):
    """Pydantic schema for tool registration requests."""

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
