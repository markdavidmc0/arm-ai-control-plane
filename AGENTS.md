# AGENTS.md — Arm Federated AI Platform

This document establishes mandatory coding standards, architectural patterns, and execution verification steps for developers and AI agents operating on this repository.

---

## 🤖 AI Agent Operating Rules
1. **Mandatory Pre-Commit Verification:** Always run `uv run ruff check`, `uv run ty check`, and `uv run pytest tests/unit` before declaring a task complete.
2. **Assertion Safeguard:** Never modify or delete existing test assertions to make broken production code pass.
3. **Documentation Compliance:** Write strict Google-style docstrings for all new public modules, classes, and functions.
4. **Plane Decoupling:** Never import runtime Python modules across plane boundaries (`src/control_plane` must never import directly from `src/data_plane`). Communication occurs strictly via HTTP/2 JSON-RPC contracts.

---

## 📂 Key Repository Paths
* `src/control_plane/` — Stateless API Gateway, auth, FastAPI routers, and MCP tool discovery interfaces.
* `src/data_plane/` — FastMCP worker engine, gVisor (`runsc`) sandbox orchestration, and tool execution runtime.
* `infra/` — Declarative IaC configurations divided by environment (`infra/terraform/`, `infra/helm/`, `infra/docker/`).
* `tests/` — Hierarchical test suites split into `unit/` (isolated package checks), `integration/` (contract tests), and `e2e/` (KinD/GKE cluster checks).
* `.agents/skills/` — Domain-namespaced context skills for automated AI agent tasks.

---

## 🎯 Domain Skill Routing
When operating on specific sub-components, load and prioritize context from `.agents/skills/`:

* **Cross-Cutting Concerns:** Load `shared-logfire-instrumentation` and `shared-uv-workspace`.
* **Control Plane (`src/control_plane`):** Load `control-plane-auth` and `control-plane-routing`. Focus on zero-trust token validation, API routing latency, and OpenAPI schemas.
* **Data Plane (`src/data_plane`):** Load `data-plane-gvisor-runtime` and `data-plane-fastmcp-worker`. Focus on sandbox isolation, CPU/RAM resource limits, and stdin/stdout RPC transport.

---

## 🐍 1. Environment, Tooling & Quality Standards
* **`uv` Package Management:** Use `uv` exclusively for environment management, workspace dependency resolution, and execution. Never run direct `pip` commands.
  * Sync workspace: `uv sync`
  * Add sub-package dependency: `uv add --package control_plane "package_name"`
  * Run unit tests: `uv run pytest tests/unit`
* **Linting & Formatting:** Run `uv run ruff check` and `uv run ruff format` to enforce PEP 8 and quality rules.
* **Static Type Checking:** Run `uv run ty check` for rapid static type verification. All production functions must include explicit type annotations for parameters and return values.

---

## 📝 2. Documentation Standards
* **Google Docstring Format:** Require Google-formatted docstrings across all public modules, classes, and functions. Explicitly outline arguments, return values, and fast-failing exceptions.

```python
def dispatch_mcp_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Executes an MCP tool action within the sandboxed data plane engine.

    Args:
        tool_name: The domain-namespaced identifier of the tool to invoke.
        payload: Parameter mapping required by the target FastMCP tool.

    Returns:
        A dictionary containing the JSON-RPC execution result payload.

    Raises:
        ValueError: If tool_name is unmapped or payload validation fails.
        RuntimeError: If gVisor sandbox container initialization fails.
    """
```

---

## 🛡️ 3. Production Code Integrity & Fail-Fast Principle
* **Zero Inline Mocking or Swallowed Fallbacks:** Production code (`src/`) must fail fast and raise explicit, actionable exceptions (`ValueError`, `RuntimeError`, `KeyError`) when required API keys, environment variables, or secrets are missing.
* **No Dummy Fallbacks:** Do NOT swallow missing secrets or dependencies by returning dummy dictionaries or silently switching to mock implementations in production modules.
* **Explicit Dependency Injection:** Design factory functions and services to accept explicit parameters or dependency objects. Failures must occur immediately at initial setup so Kubernetes readiness probes register infrastructure issues.

---

## 🧪 4. Testing & Mocking Standards
* **Isolated Pytest Fixtures:** All test mocking, dummy environment variables (`ANTHROPIC_API_KEY="mock-test-key"`), and test model bindings MUST live exclusively inside `tests/conftest.py` or sub-directory `conftest.py` files. Production service factories must remain 100% clean of testing logic.
* **Fast Deterministic Unit Execution:** Unit tests in `tests/unit/` must execute completely offline in $< 5$ seconds without making live network or LLM API calls.
* **Pytest Markers:** Mark tests with appropriate structural flags (`@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.e2e`, `@pytest.mark.kind`).

---

## 🏗️ 5. Infrastructure Standards
* **Secretless OIDC Workload Identity:** Never create or commit static cloud provider service account credentials. Authenticate automated CI/CD workflows using secretless OIDC Workload Identity Pools.
* **Declarative IAM & Zero Drift:** Declare all IAM policy bindings explicitly in Terraform (`infra/terraform/`). Parametrize GCP project IDs, regions, zones, and repository identifiers in `variables.tf` and `terraform.tfvars` to prevent hardcoded configuration drift.