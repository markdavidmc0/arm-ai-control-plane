import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.control_plane.routers.llm_proxy import router as llm_proxy_router
from src.control_plane.routers.mcp_router import router as mcp_router
from src.control_plane.routers.tool_registration import router as tool_registration_router
from src.control_plane.schemas import ControlPlaneHealthResponse

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mvcp.main")

app = FastAPI(
    title="Minimum Viable Control Plane (MVCP)",
    description="Centralized Control Plane routing Mobile AI orchestration & agent workflows.",
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

# Register Active Control Plane Routers
app.include_router(llm_proxy_router)
app.include_router(tool_registration_router)
app.include_router(mcp_router, prefix="/api/v1")


@app.get("/health", response_model=ControlPlaneHealthResponse)
@app.get("/api/v1/health", response_model=ControlPlaneHealthResponse)
async def health_check() -> ControlPlaneHealthResponse:
    """Returns the Control Plane API gateway readiness state."""
    return ControlPlaneHealthResponse(
        status="healthy",
        identity_layer="keycloak_wif",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
