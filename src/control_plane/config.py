"""Control Plane Configuration & Environment Settings."""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Control Plane operational settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATA_PLANE_URL: str = os.getenv(
        "DATA_PLANE_URL",
        os.getenv(
            "DATA_PLANE_MCP_URL",
            "http://mcp-tool-server-service.data-plane.svc.cluster.local:8000",
        ),
    )


@lru_cache
def get_settings() -> Settings:
    """Returns cached Settings instance."""
    return Settings()
