# AGENTS.md — Arm Federated AI Control Plane (`arm-federated-ai`)

This document establishes mandatory coding standards, architectural patterns, and execution verification steps for developers and AI agents operating on this repository.

---

## 🤖 AI Agent Operating Rules
1. **Mandatory Pre-Commit Verification:** Always run `uv run ruff check`, `uv run ty check`, and `uv run pytest` before declaring a task finished.
2. **Assertion Safeguard:** Never modify or delete existing test assertions to make broken production code pass.
3. **Documentation Compliance:** Write strict Google-style docstrings for all new public modules, classes, and functions.

---

## 📂 Key Repository Paths
* `src/` — Production source code (`AgentFactory`, `LocalToolDispatcher`, `SandboxOrchestrator`).
* `tests/` — Test suites, fixtures, and offline mocks (`conftest.py`).
* `terraform/` — IaC configurations (`iam.tf`, `variables.tf`, `terraform.tfvars`).

---

## 🐍 1. Environment, Tooling & Quality Standards
* **`uv` Package Management:** Use `uv` exclusively for environment management, dependency resolution, and execution. Never run direct `pip` commands.
  * Sync environment: `uv sync`
  * Add dependency: `uv add "package_name"`
  * Run tests: `uv run pytest`
* **Linting & Formatting:** Run `uv run ruff check` and `uv run ruff format` to ensure strict PEP 8 and code-quality compliance.
* **Static Type Checking:** Run `uv run ty check` for static type verification. All production functions must include explicit type annotations for parameters and return values.
* **Strict Pydantic API Schemas (`schemas.py`):**
  - All FastAPI request and response payloads MUST use explicit Pydantic `BaseModel` subclasses in `src/control_plane/schemas.py`.
  - **Never** use untyped raw `dict` objects or manual `await request.json()` parsing in API handlers.
  - Maintain a clean architectural separation:
    - **`schemas.py`**: External API Data Transfer Objects (DTOs) and request/response contracts (`MCPJsonRPCRequest`, `MCPJsonRPCResponse`).
    - **`types.py`**: Internal domain models, dependency injection containers (`ArmPlatformDeps`), and system type aliases.

---

## 📝 2. Documentation Standards
* **Google Docstring Format:** Require Google-formatted docstrings across all modules, classes, and functions. Explicitly outline arguments, return values, and fast-failing exceptions.

```python
def dispatch_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Executes a local tool action within the sandbox environment.

    Args:
        tool_name: The identifier of the tool to invoke.
        payload: Keyword argument mapping required by the tool.

    Returns:
        A dictionary containing execution outputs.

    Raises:
        ValueError: If tool_name is unknown or payload validation fails.
    """
    ...
```

---

## 🛡️ 3. Production Code Integrity & Fail-Fast Principle
* **Zero Inline Mocking or Fallback Logic in Production:**
  * Production code (`src/`) must fail fast and raise explicit, actionable exceptions (`ValueError`, `RuntimeError`, `KeyError`) when required API keys, environment variables, or secrets are missing.
  * Do NOT swallow missing secrets or dependencies by returning dummy dictionaries or silently switching to mock models in production modules.
* **Explicit Overrides & Dependency Injection:**
  * Design factory functions and services to accept explicit parameters or dependency injection objects (`ArmPlatformDeps`, `model_name`).
  * Failures must occur immediately at initial setup so Kubernetes probes and monitoring tools register infrastructure issues.

---

## 🧪 4. Testing & Mocking Standards
* **Isolated Pytest Fixtures (`tests/conftest.py`):**
  * All test mocking, dummy environment variables (`ANTHROPIC_API_KEY="mock-test-key"`), and test model bindings MUST live exclusively inside `tests/conftest.py` or `tests/` directory files.
  * Production service factories must remain 100% clean of testing logic.
* **Offline & Deterministic Unit Test Execution:**
  * The `pytest` suite must execute completely offline in < 30 seconds without making paid external network or LLM API calls.

---

## 🏗️ 5. Terraform & Infrastructure Standards
* **Strict Declarative IaC Principle (No Out-of-Band `gcloud` Provisioning):**
  * ALL cloud infrastructure (GKE clusters, node pools, IAM policy bindings, Workload Identity pools, Artifact Registry repositories, Cloud DNS, firewalls) MUST be declared exclusively in Terraform files (`terraform/`).
  * **NEVER** create, update, or modify live GCP infrastructure using direct `gcloud` or GCP Console manual commands. All changes must originate from declarative Terraform code and be applied via `terraform apply` or Terraform automation to guarantee zero infrastructure drift.
* **Secretless OIDC Workload Identity Federation:**
  * Never create or commit static GCP service account JSON key files.
  * Authenticate GitHub Actions workflows using secretless OIDC Workload Identity Pools with explicit repository bindings (`attribute.repository/OWNER/REPO`).
* **Declarative IAM & Zero Infrastructure Drift:**
  * Declare all IAM policy bindings explicitly in Terraform (`terraform/iam.tf`).
  * Parametrize GCP project IDs, regions, zones, and repository identifiers in `variables.tf` and `terraform.tfvars` to prevent hardcoded configuration drift.
