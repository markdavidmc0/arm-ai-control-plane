"""E2E Test Fixtures for Two-Tier Testing Strategy.

Provides a unified async api_client fixture that executes in-memory via
httpx.ASGITransport for fast PR gate smoke tests, or over TCP HTTP to a live cluster.
"""

import os

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.control_plane.main import app

GATEWAY_BASE_URL = os.getenv("GATEWAY_BASE_URL", "in-memory")
E2E_TARGET = os.getenv("E2E_TARGET", "inmemory").lower()


@pytest_asyncio.fixture
async def api_client():
    """Provides an HTTP client for testing.

    Defaults to In-Memory ASGI execution for fast, deterministic smoke tests.
    If GATEWAY_BASE_URL points to an external HTTP URL (e.g. http://localhost:8080),
    connects over TCP to the running live cluster service.
    """
    if GATEWAY_BASE_URL == "in-memory" or not GATEWAY_BASE_URL.startswith("http"):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            yield client
    else:
        async with AsyncClient(base_url=GATEWAY_BASE_URL, timeout=30.0) as client:
            yield client
