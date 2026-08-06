"""Global configuration settings for Data Plane and Code Mode."""

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Data Plane and Code Mode configuration settings."""

    model_config = SettingsConfigDict(env_prefix="WORKSPACE_")

    ENABLE_CODE_MODE: bool = True
    MONTY_MAX_INSTRUCTIONS: int = 1_000_000


settings = Settings()


def resolve_tools_dir(explicit_path: str | Path | None = None) -> Path:
    """Resolves the tool catalog directory using 3-tier precedence.

    Precedence:
    1. Explicit path parameter (if non-None)
    2. ARM_TOOLS_DIR environment variable
    3. Fallback to Path.cwd() / "configs"
    """
    if explicit_path is not None:
        return Path(explicit_path)
    if "ARM_TOOLS_DIR" in os.environ and os.environ["ARM_TOOLS_DIR"]:
        return Path(os.environ["ARM_TOOLS_DIR"])
    return Path.cwd() / "configs"
