import asyncio
import json
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from src.control_plane.orchestrator import SandboxOrchestrator

# Import APIRouters
from src.control_plane.routers.auth import router as auth_router
from src.control_plane.routers.llm_proxy import router as llm_proxy_router
from src.control_plane.routers.mcp_registry import router as mcp_registry_router
from src.control_plane.services.mcp_server import MCPServer, mcp

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mvcp.main")

app = FastAPI(
    title="Minimum Viable Control Plane (MVCP)",
    description="Centralized Control Plane managing GKE-sandboxed Mobile AI cross-compilation workloads.",
    version="1.0.0",
)

# Enable CORS for frontend and API gateway integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Consolidated Control Plane Routers
app.include_router(auth_router)
app.include_router(mcp_registry_router)
app.include_router(llm_proxy_router)

# Instantiate Core Engines
orchestrator = SandboxOrchestrator()
mcp_server = MCPServer(orchestrator=orchestrator)

# Mount the FastMCP Streamable HTTP / SSE Sub-Application

app.mount("/mcp", mcp.http_app())

from src.control_plane.schemas import (
    HealthStatusResponse,
    MCPJsonRPCRequest,
    MCPJsonRPCResponse,
    SSETeardownResponse,
)


@app.post("/api/v1/mcp", response_model=MCPJsonRPCResponse)
async def handle_mcp_rpc(payload: MCPJsonRPCRequest):
    """Exposes a unified HTTP gateway for Model Context Protocol (MCP) JSON-RPC 2.0."""
    body = payload.model_dump()
    response = await mcp_server.handle_mcp_request(body)
    return response


@app.get("/api/v1/mcp/sse")
async def mcp_sse_endpoint(request: Request):
    """GET endpoint for establishing a standard MCP SSE transport session."""
    session_id = str(uuid.uuid4())
    logger.info(f"Establishing new standard MCP SSE transport session: {session_id}")

    base_url = str(request.base_url).rstrip("/")
    message_endpoint = f"{base_url}/api/v1/mcp/message?session_id={session_id}"

    async def event_generator():
        try:
            yield f"event: endpoint\ndata: {message_endpoint}\n\n"
            while True:
                await asyncio.sleep(15.0)
                yield ": ping\n\n"
        except asyncio.CancelledError:
            logger.info(f"Standard MCP SSE session canceled: {session_id}")

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/v1/mcp/sse", response_model=MCPJsonRPCResponse)
async def mcp_sse_post_direct(payload: MCPJsonRPCRequest, session_id: str | None = None):
    """POST endpoint for clients that directly submit message packets to the SSE endpoint."""
    body = payload.model_dump()
    logger.info(
        f"Processing direct SSE POST payload for session {session_id}: {body.get('method')}"
    )
    response = await mcp_server.handle_mcp_request(body)
    return response


@app.delete("/api/v1/mcp/sse", response_model=SSETeardownResponse)
async def mcp_sse_delete_direct(session_id: str | None = None):
    """DELETE endpoint for clients seeking session teardown directly on the SSE endpoint."""
    logger.info(f"Processing direct SSE DELETE teardown for session {session_id}")
    return SSETeardownResponse(status="ok", message="Session terminated successfully.")


@app.post("/api/v1/mcp/message", response_model=MCPJsonRPCResponse)
async def mcp_sse_message(payload: MCPJsonRPCRequest, session_id: str):
    """POST endpoint where standard SSE transport clients deliver JSON-RPC frames."""
    body = payload.model_dump()
    logger.info(f"Processing standard SSE payload for session {session_id}: {body.get('method')}")
    response = await mcp_server.handle_mcp_request(body)
    return response


@app.post("/api/v1/mcp/stream")
async def handle_streamable_mcp(payload: MCPJsonRPCRequest):
    """Consolidated Single-Connection Streamable HTTP Gateway."""
    body = payload.model_dump()

    async def rpc_streamer(body_data):
        try:
            response = await mcp_server.handle_mcp_request(body_data)
            yield json.dumps(response) + "\n"
        except Exception as e:
            error_frame = {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": f"Stream connection crashed: {str(e)}",
                },
            }
            yield json.dumps(error_frame) + "\n"

    return StreamingResponse(rpc_streamer(body), media_type="application/x-ndjson")


@app.get("/api/v1/health", response_model=HealthStatusResponse)
async def health_check():
    """Returns the API gateway readiness state."""
    return HealthStatusResponse(
        status="healthy",
        gke_orchestrator_connected=orchestrator.k8s_client_configured,
        identity_layer="tailscale_tsnet",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
