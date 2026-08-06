"""Unified Operational Configuration for Control Plane and Data Plane."""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Platform-wide operational settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Feature Flags & Engine Limits
    ENABLE_CODE_MODE: bool = False
    MONTY_MAX_INSTRUCTIONS: int = 1_000_000

    # Networking & Service Resolution
    DATA_PLANE_URL: str = Field(
        default="http://mcp-tool-server-service.data-plane.svc.cluster.local:8000",
        validation_alias=AliasChoices("DATA_PLANE_URL", "DATA_PLANE_MCP_URL"),
    )


@lru_cache
def get_settings() -> Settings:
    """Returns cached global Settings instance."""
    return Settings()


settings = get_settings()


def resolve_tools_dir(explicit_path: str | Path | None = None) -> Path:
    """Resolves the tool catalog directory using 3-tier precedence.

    Precedence:
    1. Explicit path parameter (if non-None)
    2. ARM_TOOLS_DIR environment variable
    3. Fallback to Path.cwd() / "configs"
    """
    if explicit_path is not None:
        return Path(explicit_path)
    if os.getenv("ARM_TOOLS_DIR"):
        return Path(os.environ["ARM_TOOLS_DIR"])
    return Path.cwd() / "configs"
