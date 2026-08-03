"""Control Plane API Request and Response Pydantic Schemas & Type Definitions."""

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field


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


class MCPJsonRPCRequest(BaseModel):
    """Pydantic schema for incoming MCP JSON-RPC 2.0 requests."""

    jsonrpc: str = Field("2.0", description="JSON-RPC protocol version")
    id: str | int | None = Field(None, description="Optional request ID")
    method: str = Field(
        ..., description="Target MCP method name (e.g., 'tools/call', 'tools/list')"
    )
    params: dict[str, Any] = Field(default_factory=dict, description="Method parameters")


class MCPJsonRPCResponse(BaseModel):
    """Pydantic schema for outgoing MCP JSON-RPC 2.0 responses."""

    jsonrpc: str = Field("2.0", description="JSON-RPC protocol version")
    id: str | int | None = Field(None, description="Corresponding request ID")
    result: Any | None = Field(None, description="Successful result payload")
    error: dict[str, Any] | None = Field(None, description="JSON-RPC error payload")


class ToolExecutionRequest(BaseModel):
    """Pydantic schema for direct local tool dispatch requests."""

    tool_name: str = Field(..., description="Target tool name to invoke")
    payload: dict[str, Any] = Field(
        default_factory=dict, description="Keyword arguments for tool execution"
    )


class HealthStatusResponse(BaseModel):
    """Pydantic schema for control plane health readiness responses."""

    status: str = Field("healthy", description="Gateway readiness status")
    gke_orchestrator_connected: bool = Field(
        ..., description="Whether GKE Kubernetes API client is connected"
    )
    identity_layer: str = Field("tailscale_tsnet", description="Identity and mesh network provider")


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
    """Pydantic schema for streaming progress notifications."""

    jsonrpc: str = Field("2.0", description="JSON-RPC protocol version")
    method: str = Field("notifications/progress", description="Notification method slug")
    params: ProgressNotificationParams = Field(..., description="Notification parameter object")
