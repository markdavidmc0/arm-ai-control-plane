"""Control Plane API Request and Response Pydantic Schemas & Type Definitions."""

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


@dataclass
class ArmPlatformDeps:
    """Dependency injection container passed to Pydantic AI agent runs.

    Holds active session tokens, user/workspace metadata, and references
    to orchestrator & multiplexer services.
    """

    session_id: str
    workspace_context: str = "cloud-ai"
    user_id: str = "default-user"
    mcp_multiplexer: Any = None
    orchestrator: Any = None


class JSONRPCError(BaseModel):
    """Standard JSON-RPC 2.0 Error object schema."""

    model_config = ConfigDict(extra="ignore")

    code: int = Field(..., description="JSON-RPC error code (e.g., -32601 Method Not Found)")
    message: str = Field(..., description="Short description of the error")
    data: Any | None = Field(None, description="Optional detailed error context or trace")


class MCPJsonRPCRequest(BaseModel):
    """Pydantic schema for incoming MCP JSON-RPC 2.0 requests."""

    model_config = ConfigDict(extra="ignore")

    jsonrpc: Literal["2.0"] = Field("2.0", description="JSON-RPC protocol version")
    id: str | int | None = Field(None, description="Optional request ID (None for notifications)")
    method: str = Field(
        ..., description="Target MCP method name (e.g., 'tools/call', 'tools/list')"
    )
    params: dict[str, Any] = Field(default_factory=dict, description="Method parameters")


class MCPJsonRPCResponse(BaseModel):
    """Pydantic schema for outgoing MCP JSON-RPC 2.0 responses."""

    model_config = ConfigDict(extra="ignore")

    jsonrpc: Literal["2.0"] = Field("2.0", description="JSON-RPC protocol version")
    id: str | int | None = Field(..., description="Corresponding request ID")
    result: Any | None = Field(None, description="Successful result payload")
    error: JSONRPCError | None = Field(None, description="Structured JSON-RPC error payload")


class ToolExecutionRequest(BaseModel):
    """Pydantic schema for direct local tool dispatch requests."""

    tool_name: str = Field(..., description="Target tool name to invoke")
    payload: dict[str, Any] = Field(
        default_factory=dict, description="Keyword arguments for tool execution"
    )


class SandboxExecutionRequest(BaseModel):
    """Pydantic schema for sandboxed Python code execution requests."""

    script: str = Field(..., description="Python script payload to execute in gVisor sandbox")
    timeout_seconds: int = Field(10, ge=1, le=120, description="Execution timeout limit")


class SandboxExecutionResponse(BaseModel):
    """Pydantic schema for sandboxed execution output."""

    status: str = Field(..., description="Execution status slug ('SUCCESS', 'ERROR', 'TIMEOUT')")
    exit_code: int = Field(..., description="Process exit code (0 for success)")
    output: str | None = Field(None, description="Captured stdout/stderr stream output")
    error: str | None = Field(None, description="Sandbox failure detail if applicable")


class ToolRegistryResponse(BaseModel):
    """Pydantic schema for registered tool listing responses."""

    tools: list[dict[str, Any]] = Field(..., description="List of registered tool metadata objects")
    tool_count: int = Field(..., description="Total count of active registered tools")
    workspace: str = Field(..., description="Active workspace context slug")


class HealthStatusResponse(BaseModel):
    """Pydantic schema for control plane health readiness responses."""

    status: str = Field("healthy", description="Gateway readiness status")
    gke_orchestrator_connected: bool = Field(
        ..., description="Whether GKE Kubernetes API client is connected"
    )
    identity_layer: str = Field(
        "keycloak_wif", description="Identity and OIDC Workload Identity Federation provider"
    )


class SSETeardownResponse(BaseModel):
    """Pydantic schema for SSE transport session teardown responses."""

    status: str = Field("ok", description="Teardown status slug")
    message: str = Field(..., description="Confirmation message")


class ProgressNotificationParams(BaseModel):
    """Payload params for progress notifications during streaming execution."""

    status: str = Field(
        ..., description="Execution status slug ('compiling', 'optimizing_assembly')"
    )
    sandbox_health: str = Field(..., description="Sandbox environment health code")


class ProgressNotificationFrame(BaseModel):
    """Pydantic schema for streaming progress notifications (no ID per spec)."""

    jsonrpc: Literal["2.0"] = Field("2.0", description="JSON-RPC protocol version")
    method: str = Field("notifications/progress", description="Notification method slug")
    params: ProgressNotificationParams = Field(..., description="Notification parameter object")
