"""Unit tests for resolve_tools_dir helper and Control Plane tool registration endpoint."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.config import resolve_tools_dir
from src.control_plane.main import app

client = TestClient(app)


@pytest.mark.unit
def test_resolve_tools_dir_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies 3-tier precedence: explicit_path > ARM_TOOLS_DIR env var > cwd/configs fallback."""
    explicit_dir = tmp_path / "explicit_tools"
    env_dir = tmp_path / "env_tools"

    # Tier 1: Explicit path parameter takes top priority
    monkeypatch.setenv("ARM_TOOLS_DIR", str(env_dir))
    res_explicit = resolve_tools_dir(explicit_path=explicit_dir)
    assert res_explicit == explicit_dir

    # Tier 2: ARM_TOOLS_DIR takes priority when explicit_path is None
    res_env = resolve_tools_dir(explicit_path=None)
    assert res_env == env_dir

    # Tier 3: Fallback to Path.cwd() / "configs" when both are unset
    monkeypatch.delenv("ARM_TOOLS_DIR", raising=False)
    res_fallback = resolve_tools_dir(explicit_path=None)
    assert res_fallback == Path.cwd() / "configs"


@pytest.mark.unit
def test_tool_registration_endpoint_atomic_upsert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies POST /api/v1/tools/register atomic upsert and {"tools": [...]} schema formatting."""
    target_dir = tmp_path / "custom_tools_dir"
    monkeypatch.setenv("ARM_TOOLS_DIR", str(target_dir))

    # 1. Register a new tool
    payload1 = {
        "name": "vector_accelerator",
        "description": "Arm SME2 vector acceleration kernel",
        "parameters": {
            "type": "object",
            "properties": {"vector_len": {"type": "integer"}},
        },
        "entrypoint": "bin/vector_accel",
    }

    response1 = client.post("/api/v1/tools/register", json=payload1)
    assert response1.status_code == 200
    res_data1 = response1.json()
    assert res_data1["status"] == "registered"
    assert res_data1["tool"]["name"] == "vector_accelerator"
    assert res_data1["tool"]["entrypoint"] == "bin/vector_accel"

    catalog_path = target_dir / "catalog.json"
    assert catalog_path.exists()

    with open(catalog_path, encoding="utf-8") as f:
        catalog_json = json.load(f)

    assert "tools" in catalog_json
    assert len(catalog_json["tools"]) == 1
    tool1 = catalog_json["tools"][0]
    assert tool1["name"] == "vector_accelerator"
    assert tool1["parameters"] == payload1["parameters"]
    assert tool1["inputSchema"] == payload1["parameters"]
    assert tool1["entrypoint"] == "bin/vector_accel"

    # 2. Update existing tool (Upsert)
    payload1_updated = {
        "name": "vector_accelerator",
        "description": "Updated Arm SME2 vector acceleration kernel v2",
        "parameters": {
            "type": "object",
            "properties": {"vector_len": {"type": "integer"}, "tile_size": {"type": "integer"}},
        },
        "entrypoint": "bin/vector_accel_v2",
    }

    response1_up = client.post("/api/v1/tools/register", json=payload1_updated)
    assert response1_up.status_code == 200

    with open(catalog_path, encoding="utf-8") as f:
        catalog_json_up = json.load(f)

    assert len(catalog_json_up["tools"]) == 1
    tool1_up = catalog_json_up["tools"][0]
    assert tool1_up["description"] == "Updated Arm SME2 vector acceleration kernel v2"
    assert tool1_up["entrypoint"] == "bin/vector_accel_v2"

    # 3. Append a second new tool
    payload2 = {
        "name": "kernel_profiler",
        "description": "Profiles N2 PMU counters",
        "parameters": {},
    }

    response2 = client.post("/api/v1/tools/register", json=payload2)
    assert response2.status_code == 200

    with open(catalog_path, encoding="utf-8") as f:
        catalog_json_final = json.load(f)

    assert len(catalog_json_final["tools"]) == 2
    tool_names = [t["name"] for t in catalog_json_final["tools"]]
    assert "vector_accelerator" in tool_names
    assert "kernel_profiler" in tool_names
