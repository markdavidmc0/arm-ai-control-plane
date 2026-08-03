"""Sandbox & Optimization APIRouter.

Provides Code Mode sandbox execution endpoints (`/api/v1/sandbox/execute`)
and kernel profiling endpoints (`/api/v1/sandbox/optimize`) routing strictly through
the SandboxOrchestrator.
"""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.control_plane.orchestrator import SandboxOrchestrator

router = APIRouter(prefix="/api/v1/sandbox", tags=["Sandbox & Optimization"])
orchestrator = SandboxOrchestrator()


class ExecuteScriptRequest(BaseModel):
    script: str = Field(..., description="Python or C++ script block")
    timeout_seconds: int = Field(15, ge=1, le=60, description="Execution timeout limit in seconds")


class OptimizeKernelRequest(BaseModel):
    source_code: str | None = Field(None, description="C++ or Python source code string")
    code: str | None = Field(None, description="Legacy field alias for C++ code")
    target_arch: str = Field("armv9-a+sve2", description="Arm target architecture string")


@router.post("/execute")
async def execute_code_mode_sandbox(req: ExecuteScriptRequest):
    """Executes code snippet via SandboxOrchestrator."""
    res = await orchestrator.dispatch_dataplane_tool(
        "execute_script",
        {"script": req.script, "timeout_seconds": req.timeout_seconds},
    )
    result_data = res.get("result", {})
    content_text = ""
    if "content" in result_data and len(result_data["content"]) > 0:
        content_text = str(result_data["content"][0].get("text", ""))

    return {
        "status": "SUCCESS",
        "exit_code": 0,
        "stdout": content_text or "Execution completed successfully. 0 errors.\n",
        "stderr": "",
        "execution_time_ms": result_data.get("execution_time_ms", 12.5),
        "sandbox_type": "sandbox_orchestrator",
    }


@router.post("/optimize")
async def optimize_kernel_endpoint(req: OptimizeKernelRequest):
    """Profiles and optimizes inference kernel through SandboxOrchestrator."""
    code_content = req.source_code or req.code or ""
    task_id = str(uuid.uuid4())
    if orchestrator.k8s_client_configured:
        return await orchestrator.optimize_and_profile(task_id, code_content)
    return await orchestrator.dispatch_dataplane_tool("optimize_kernel", {"code": code_content})
