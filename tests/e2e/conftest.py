"""E2E Test Fixtures for Two-Tier Testing Strategy.

Provides CLI flag parsing, target environment resolution, and dynamic api_client fixture.
"""

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.control_plane.main import app


@pytest.fixture
def target_env(request) -> str:
    """Resolves target environment from CLI flag --target or E2E_TARGET env var."""
    cli_target = request.config.getoption("--target", None)
    if cli_target and cli_target != "inmemory":
        return cli_target.lower()
    return os.getenv("E2E_TARGET", "inmemory").lower()


@pytest.fixture
def gateway_url(request, target_env) -> str:
    """Resolves Gateway base URL from CLI flag --endpoint or GATEWAY_BASE_URL env var."""
    cli_endpoint = request.config.getoption("--endpoint", None)
    if cli_endpoint:
        return cli_endpoint
    env_url = os.getenv("GATEWAY_BASE_URL", None)
    if env_url:
        return env_url
    if target_env in ["kind", "live_gke", "cluster"]:
        return "http://localhost:8080"
    return "in-memory"


@pytest.fixture
def llm_enabled(request, target_env) -> bool:
    """Checks if live LLM credentials are present and target allows benchmark execution."""
    run_benchmarks = request.config.getoption("--run-benchmarks", False)
    if run_benchmarks:
        return True

    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY", "")

    has_real_key = bool(
        (anthropic_key and not anthropic_key.startswith("mock-"))
        or (openai_key and not openai_key.startswith("mock-"))
    )

    if target_env == "live_gke":
        return has_real_key
    return False


@pytest_asyncio.fixture
async def api_client(target_env, gateway_url):
    """Provides an HTTP client for testing.

    Yields an ASGITransport client for inmemory execution,
    or an httpx.AsyncClient connected to the cluster gateway URL.
    """
    if target_env == "inmemory" or gateway_url == "in-memory" or not gateway_url.startswith("http"):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            yield client
    else:
        async with AsyncClient(base_url=gateway_url, timeout=30.0) as client:
            yield client
