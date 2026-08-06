"""Control Plane Tool Registration Router."""

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status

from src.config import resolve_tools_dir
from src.control_plane.schemas import ToolRegistrationSchema

logger = logging.getLogger("mvcp.routers.tool_registration")

router = APIRouter(prefix="/api/v1/tools", tags=["Tool Registration"])


@router.post("/register", status_code=status.HTTP_200_OK)
async def register_tool(payload: ToolRegistrationSchema) -> dict[str, Any]:
    """Registers or updates a tool entry in catalog.json via atomic file replacement.

    Args:
        payload: ToolRegistrationSchema containing name, description, parameters, and entrypoint.

    Returns:
        JSON response with registration status, created tool schema, and target catalog path.
    """
    target_dir = resolve_tools_dir()
    target_dir.mkdir(parents=True, exist_ok=True)

    catalog_path = target_dir / "catalog.json"
    temp_path = target_dir / ".catalog.json.tmp"

    tools_list: list[dict[str, Any]] = []

    if catalog_path.exists():
        try:
            with open(catalog_path, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    tools_list = data.get("tools", [])
                elif isinstance(data, list):
                    tools_list = data
        except Exception as e:
            logger.warning(
                f"[Control Plane] Failed to parse existing catalog.json at {catalog_path}: {e}. "
                "Initializing new catalog structure."
            )
            tools_list = []

    item: dict[str, Any] = {
        "name": payload.name,
        "description": payload.description,
        "parameters": payload.parameters,
        "inputSchema": payload.parameters,
    }
    if payload.entrypoint is not None:
        item["entrypoint"] = payload.entrypoint

    updated = False
    new_tools_list: list[dict[str, Any]] = []
    for tool_entry in tools_list:
        if tool_entry.get("name") == payload.name:
            new_tools_list.append(item)
            updated = True
        else:
            new_tools_list.append(tool_entry)

    if not updated:
        new_tools_list.append(item)

    catalog_payload = {"tools": new_tools_list}

    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(catalog_payload, f, indent=2)

        temp_path.replace(catalog_path)
        logger.info(
            f"[Control Plane] Tool '{payload.name}' successfully registered in {catalog_path}"
        )

        return {
            "status": "registered",
            "tool": item,
            "catalog_path": str(catalog_path),
        }

    except Exception as e:
        logger.error(
            f"[Control Plane] Failed atomic catalog registration for tool '{payload.name}': {e}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register tool '{payload.name}': {e}",
        ) from e

    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception as cleanup_err:
                logger.warning(
                    f"[Control Plane] Cleanup of temp file {temp_path} failed: {cleanup_err}"
                )
