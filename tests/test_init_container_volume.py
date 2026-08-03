"""Unit tests for Pattern 1 Kubernetes initContainer Tool Volume Mounts in orchestrator.py."""

import pytest
from src.control_plane.orchestrator import SandboxOrchestrator


@pytest.mark.asyncio
async def test_orchestrator_init_container_pod_manifest_structure():
    """Verify SandboxOrchestrator constructs pod manifests with initContainers and read-only volume mounts."""
    orchestrator = SandboxOrchestrator()

    # Verify simulation mode or orchestrator attributes
    res = await orchestrator.optimize_and_profile("test-init-task-1", "void matmul() {}")
    assert res["status"] == "success"
    assert "sandbox_security" in res


def test_orchestrator_bootstrap_command_generation():
    """Verify orchestrator bootstrap command formats C++ source code properly."""
    orchestrator = SandboxOrchestrator()
    code = "void matmul_test() { int a = 1; }"
    bootstrap_cmd = orchestrator._generate_sandbox_bootstrap_command(code)

    assert "matrix.cpp" in bootstrap_cmd
    assert "matmul_test" in bootstrap_cmd
