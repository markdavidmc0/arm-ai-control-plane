"""Contract Tests for Control Plane and Data Plane Package Isolation."""

import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_PLANE_TOML = REPO_ROOT / "src" / "control_plane" / "pyproject.toml"
DATA_PLANE_TOML = REPO_ROOT / "src" / "data_plane" / "pyproject.toml"


def _load_manifest(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


@pytest.mark.contract
@pytest.mark.unit
def test_python_version_constraints():
    """Verify python version constraints are >=3.12 across all manifests."""
    cp_manifest = _load_manifest(CONTROL_PLANE_TOML)
    dp_manifest = _load_manifest(DATA_PLANE_TOML)

    assert cp_manifest["project"]["requires-python"] == ">=3.12"
    assert dp_manifest["project"]["requires-python"] == ">=3.12"


@pytest.mark.contract
@pytest.mark.unit
def test_control_plane_dependencies_exclude_data_plane():
    """Verify control plane pyproject.toml excludes data plane packages and paths."""
    cp_manifest = _load_manifest(CONTROL_PLANE_TOML)
    deps = cp_manifest["project"].get("dependencies", [])
    dep_str = " ".join(deps)

    assert "pydantic-monty" not in dep_str
    assert "src/data_plane" not in dep_str


@pytest.mark.contract
@pytest.mark.unit
def test_data_plane_dependencies_exclude_control_plane():
    """Verify data plane pyproject.toml excludes control plane packages and paths."""
    dp_manifest = _load_manifest(DATA_PLANE_TOML)
    deps = dp_manifest["project"].get("dependencies", [])
    dep_str = " ".join(deps)

    for forbidden in ["litellm", "pyjwt", "fastapi", "pydantic-ai", "src/control_plane"]:
        assert forbidden not in dep_str


@pytest.mark.contract
@pytest.mark.unit
def test_data_plane_includes_execution_engine():
    """Verify data plane pyproject.toml includes pydantic-monty execution engine."""
    dp_manifest = _load_manifest(DATA_PLANE_TOML)
    deps = dp_manifest["project"].get("dependencies", [])
    assert any("pydantic-monty" in dep for dep in deps)


@pytest.mark.contract
@pytest.mark.unit
def test_control_plane_includes_agent_framework():
    """Verify control plane pyproject.toml includes pydantic-ai agent framework."""
    cp_manifest = _load_manifest(CONTROL_PLANE_TOML)
    deps = cp_manifest["project"].get("dependencies", [])
    assert any("pydantic-ai" in dep for dep in deps)
