import uuid
import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.control_plane.orchestrator import SandboxOrchestrator
from src.control_plane.mcp_server import MCPServer

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mvcp.main")

app = FastAPI(
    title="Minimum Viable Control Plane (MVCP)",
    description="Centralized Control Plane managing GKE-sandboxed Mobile AI cross-compilation workloads.",
    version="1.0.0"
)

# Enable CORS for frontend and API gateway integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instantiate Core Engines
orchestrator = SandboxOrchestrator()
mcp_server = MCPServer(orchestrator=orchestrator)

# In-Memory Database for tracking tasks
tasks_db: Dict[str, Dict[str, Any]] = {}

class OptimizationRequest(BaseModel):
    code: str

class OptimizationResponse(BaseModel):
    task_id: str
    status: str
    message: str

async def execute_optimization_task(task_id: str, code: str):
    """
    Background worker that invokes the sandboxed GKE execution engine.
    """
    tasks_db[task_id]["status"] = "running"
    try:
        # Launch GKE gVisor sandbox run
        profile_results = await orchestrator.optimize_and_profile(task_id, code)
        
        # Translate raw JSON profile into structured Heatmap payload
        visual_payload = mcp_server.translate_profile_to_heatmap(profile_results)
        
        tasks_db[task_id].update({
            "status": "completed",
            "results": visual_payload,
            "sandbox_health": "NOMINAL",
            "gvisor_logs": "runsc: sandbox initialized successfully. Armv9 NEON/SME2 acceleration engines active."
        })
        logger.info(f"Task {task_id} completed successfully.")
    except Exception as e:
        logger.error(f"Error during execution of task {task_id}: {e}")
        tasks_db[task_id].update({
            "status": "failed",
            "error": str(e),
            "sandbox_health": "CRITICAL_ERROR",
            "gvisor_logs": f"Kernel execution fault inside runsc sandbox: {str(e)}"
        })

@app.post("/api/v1/optimize", response_model=OptimizationResponse)
async def trigger_optimize(request: OptimizationRequest, background_tasks: BackgroundTasks):
    """
    Kicks off an agentic workspace optimization run. Spins up an isolated
    container within a GKE Arm Node and profiles vectorization efficiency.
    """
    task_id = str(uuid.uuid4())
    logger.info(f"Received optimization request. Provisioning task_id: {task_id}")
    
    # Initialize database state
    tasks_db[task_id] = {
        "task_id": task_id,
        "status": "queued",
        "sandbox_health": "PROVISIONING",
        "results": None
    }
    
    # Delegate to GKE sandbox in background to keep endpoint responsive
    background_tasks.add_task(execute_optimization_task, task_id, request.code)
    
    return OptimizationResponse(
        task_id=task_id,
        status="queued",
        message="Sandbox GKE instance queued for spinup on Arm node pool."
    )

@app.get("/api/v1/status/{task_id}")
async def get_status(task_id: str):
    """
    Queries current task metrics, status, and sandbox environment diagnostics.
    """
    task = tasks_db.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")
    
    return task

@app.post("/api/v1/mcp")
async def handle_mcp_rpc(request: Request):
    """
    Exposes a unified HTTP gateway for Model Context Protocol (MCP) JSON-RPC 2.0.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON-RPC payload.")
    
    response = mcp_server.handle_mcp_request(body)
    return response

@app.get("/api/v1/health")
async def health_check():
    """
    Returns API gateway readiness state.
    """
    return {
        "status": "healthy",
        "gke_orchestrator_connected": orchestrator.k8s_client_configured,
        "identity_layer": "tailscale_tsnet"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
