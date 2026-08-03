"""Unit tests for Pattern 1 Kubernetes initContainer Tool Volume Mounts in orchestrator.py."""

from src.control_plane.orchestrator import SandboxOrchestrator


def test_orchestrator_init_container_pod_manifest_structure():
    """Verify SandboxOrchestrator constructs pod manifests with initContainers and read-only volume mounts."""
    orchestrator = SandboxOrchestrator()

    manifest = orchestrator.build_pod_manifest(
        "test-init-task-1", "void matmul() {}", execution_mode="codemode"
    )
    assert manifest["kind"] == "Pod"
    assert manifest["spec"]["initContainers"][0]["name"] == "tools-installer"
    assert manifest["spec"]["containers"][0]["volumeMounts"][0]["readOnly"] is True


def test_orchestrator_execution_mode_direct_omits_init_containers():
    """Verify build_pod_manifest omits initContainers and volumeMounts when execution_mode='direct'."""
    orchestrator = SandboxOrchestrator()
    manifest_direct = orchestrator.build_pod_manifest(
        "test-direct-task", "void matmul() {}", execution_mode="direct"
    )
    assert manifest_direct["spec"]["initContainers"] == []
    assert manifest_direct["spec"]["volumes"] == []
    assert manifest_direct["spec"]["containers"][0]["volumeMounts"] == []


def test_orchestrator_bootstrap_command_generation():
    """Verify orchestrator bootstrap command formats C++ source code safely with base64."""
    orchestrator = SandboxOrchestrator()
    code = "void matmul_test() { int a = 1; }"
    bootstrap_cmd = orchestrator._generate_sandbox_bootstrap_command(code)

    assert "matrix.cpp" in bootstrap_cmd
    assert "base64.b64decode" in bootstrap_cmd
    import base64

    encoded = base64.b64encode(code.encode("utf-8")).decode("utf-8")
    assert encoded in bootstrap_cmd
