"""gVisor Sandbox & Optimization APIRouter.

Provides Code Mode sandbox execution endpoints (`/api/v1/sandbox/execute`)
and synchronous kernel profiling endpoints (`/api/v1/sandbox/optimize`).
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from src.control_plane.services.gvisor_runner import GVisorRunnerService

router = APIRouter(prefix="/api/v1/sandbox", tags=["gVisor Sandbox & Optimization"])
runner_service = GVisorRunnerService()


class ExecuteScriptRequest(BaseModel):
    script: str = Field(..., description="Python or C++ script block")
    timeout_seconds: int = Field(15, ge=1, le=60, description="Execution timeout limit in seconds")


class OptimizeKernelRequest(BaseModel):
    source_code: str | None = Field(None, description="C++ or Python source code string")
    code: str | None = Field(None, description="Legacy field alias for C++ code")
    target_arch: str = Field("armv9-a+sve2", description="Arm target architecture string")


@router.post("/execute")
async def execute_code_mode_sandbox(req: ExecuteScriptRequest):
    """Executes Python/C++ code snippet inside gVisor (`runsc`) container or simulation fallback."""
    res = runner_service.execute_script(script=req.script, timeout_seconds=req.timeout_seconds)
    return res


@router.post("/optimize")
async def optimize_kernel_endpoint(req: OptimizeKernelRequest):
    """Synchronously profiles and optimizes inference kernel, returning SVE2 vector metrics."""
    code_content = req.source_code or req.code or ""
    res = runner_service.optimize_kernel_rest(source_code=code_content)
    return res
