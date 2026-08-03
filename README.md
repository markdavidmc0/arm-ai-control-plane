# 🛡️ Arm Federated AI Control Plane & Data Plane Platform

[![Fast CI Gate](https://github.com/markdavidmc0/arm-ai-control-plane/actions/workflows/platform_ci_cd.yml/badge.svg)](https://github.com/markdavidmc0/arm-ai-control-plane/actions/workflows/platform_ci_cd.yml)
[![E2E Heavy Benchmarks](https://github.com/markdavidmc0/arm-ai-control-plane/actions/workflows/e2e-benchmarks.yml/badge.svg)](https://github.com/markdavidmc0/arm-ai-control-plane/actions/workflows/e2e-benchmarks.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Arm Tau T2A](https://img.shields.io/badge/architecture-Arm64--Neoverse--N2-orange.svg)](https://cloud.google.com/compute/docs/general-purpose-machines#t2a_machines)
[![gVisor Sandbox](https://img.shields.io/badge/sandbox-gVisor--runsc-green.svg)](https://gvisor.dev/)
[![Model Context Protocol](https://img.shields.io/badge/protocol-MCP--JSON--RPC--2.0-purple.svg)](https://modelcontextprotocol.io/)

An enterprise-grade, zero-trust **Federated Model Context Protocol (MCP) Control Plane & Data Plane Platform** engineered for **64-bit Arm Neoverse / Tau T2A architectures**. Combines gVisor micro-kernel sandboxing, workspace-context prompt slicing, CodeMode REPL execution, and federated MCP server aggregation on Google Kubernetes Engine (GKE).

---

## 🏛️ Core Architecture Flow (Control Plane vs. Data Plane)

The platform enforces strict architectural separation between the **Thick Gateway Control Plane** (protocol translation, zero code execution, authentication, workspace slicing, LLM proxying) and the **Isolated Data Plane** (sandboxed execution, C++/Python profiling, native tool drivers).

```
                                      CLIENTS & AI AGENTS
                               (Pydantic AI / CodeMode / FastMCP)
                                                │
                                  Bearer JWT / API Key / Headers
                                                │
  ┌─────────────────────────────────────────────▼─────────────────────────────────────────────┐
  │                                   CONTROL PLANE GATEWAY                                   │
  │                           (src/control_plane/ - Thick Gateway)                            │
  │                                                                                           │
  │   ┌────────────────────────┐  ┌─────────────────────────┐  ┌─────────────────────────┐   │
  │   │      routers/auth      │  │   routers/mcp_registry  │  │    routers/llm_router    │   │
  │   │  Envoy ext_authz &     │  │  Workspace Slicing &    │  │  Async httpx completion │   │
  │   │  Keycloak OIDC Tokens  │  │  /execute & /optimize   │  │  /v1/chat/completions   │   │
  │   └───────────┬────────────┘  └────────────┬────────────┘  └────────────┬────────────┘   │
  │               │                            │                            │                 │
  │   ┌───────────▼────────────┐  ┌────────────▼────────────┐  ┌────────────▼────────────┐   │
  │   │  services/auth_service │  │ services/mcp_multiplexer│  │   services/llm_router   │   │
  │   │  Salted SHA-256 Keys & │  │  Context Slicing (<1.5k)│  │   Token/Cost Calculator │   │
  │   │  Rate Limiting         │  │  & Upstream Proxying    │  │   ($3.00/1M baseline)   │   │
  │   └────────────────────────┘  └────────────┬────────────┘  └─────────────────────────┘   │
  │                                            │                                              │
  │                                            ▼                                              │
  │                                    orchestrator.py                                        │
  │                         (Async K8s Pod & gVisor RPC Client)                               │
  └────────────────────────────────────────────┬──────────────────────────────────────────────┘
                                               │
                           gVisor Pod Scheduling / Worker Dispatch
                                               │
  ┌────────────────────────────────────────────▼──────────────────────────────────────────────┐
  │                                     DATA PLANE WORKER                                     │
  │                      (src/data_plane/worker.py - Isolated Sandbox)                        │
  │                                                                                           │
  │   ┌──────────────────────────────┐                ┌───────────────────────────────────┐   │
  │   │    DataPlaneSandboxRunner    │                │        LocalToolDispatcher        │   │
  │   │  Monty REPL Execution Engine │                │  Catalog (/opt/arm-tools/catalog) │   │
  │   │  Top-Level Await & State     │                │  Compiler Driver & Subprocesses   │   │
  │   └──────────────┬───────────────┘                └─────────────────┬─────────────────┘   │
  │                  │                                                  │                     │
  │                  └───────────────────────┬──────────────────────────┘                     │
  │                                          │                                                │
  │                                          ▼                                                │
  │                           ┌─────────────────────────────┐                                 │
  │                           │     ArmToolsSDKBridge       │                                 │
  │                           │   arm_tools.my_tool(...)    │                                 │
  │                           │   Parallel asyncio.gather   │                                 │
  │                           └─────────────────────────────┘                                 │
  └───────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔒 Sandboxing & Runtime Isolation

Platform workloads run inside secure, transient micro-kernel sandboxes to guarantee multi-tenant security and zero side-effects on host nodes:

1. **gVisor (`runsc-arm`) vs Native (`runc-arm`)**:
   - **gVisor Isolation** (`use_gvisor=True`): Traps system calls inside an application kernel written in Go (`runsc`), executing on dedicated `arm-gvisor-sandbox` Tau T2A node pools.
   - **Native Baseline** (`use_gvisor=False`): Routes execution directly to `arm-native-baseline` node pools for unconstrained performance benchmarking.

2. **Read-Only Tool Mounts & Write-Block Enforcement**:
   - `initContainers` (`tools-installer`) copy tool binaries to `/opt/arm-tools/` during Pod startup.
   - The primary compiler container mounts `/opt/arm-tools/` as **read-only** (`readOnly: True`), blocking malicious filesystem modifications during script execution.

3. **Resource Caps & Timeouts**:
   - Pod manifests enforce strict CPU (2 vCPU) and memory limits (2GiB), with a 180-second hard timeout monitored asynchronously via `asyncio.to_thread`.

---

## 🚀 Deployment & Infrastructure

The infrastructure is declared exclusively in Terraform (`terraform/`) and deployed to Google Cloud Platform:

* **Arm Tau T2A GKE Node Pools**: 64-bit Armv8.2-A (Neoverse N2) compute nodes configured with gVisor `RuntimeClass`.
* **Private VPC & Cloud DNS**: Private service discovery via Cloud DNS (`keycloak.arm.internal` and `gateway.arm.internal`). Zero public IP exposure.
* **Envoy Edge Guard & Keycloak OIDC**: Envoy sidecar proxies execute zero-trust sidecar authentication checks (`/api/v1/internal/auth-check`) before forwarding traffic.
* **Secretless OIDC Workload Identity**: CI/CD pipelines authenticate to GCP using OIDC Workload Identity Federation without static JSON key files.

```bash
# Provision infrastructure via Terraform
cd terraform
terraform init
terraform apply \
  -var="project_id=sovereign-ai-495715" \
  -var="region=us-central1" \
  -var="zone=us-central1-a"
```

---

## 💻 CodeMode REPL & Agent Execution

The Data Plane features an advanced Python REPL runner (`DataPlaneSandboxRunner`) tailored for LLM code execution:

* **Prompt Cache Protection (`dynamic_catalog=True`)**:
  - `CodeMode` hides unneeded tool stubs during initial prompt construction, injecting discovered tools dynamically via system instructions to preserve provider KV prompt cache.
* **Top-Level `await` Support**:
  - Code snippets containing top-level `await` statements (e.g. `res = await arm_tools.profile_and_optimize_kernel(...)`) are wrapped in an async harness and evaluated without syntax errors.
* **Multi-Turn State Persistence**:
  - Variables, imports, and state created in Turn 1 persist seamlessly into Turn 2 REPL turns.
* **`arm_tools` Parallel SDK Bridge**:
  - Exposes `arm_tools.my_tool(...)` inside the REPL environment, enabling concurrent tool invocation via `asyncio.gather(arm_tools.tool1(), arm_tools.tool2())`.

---

## 🔌 Tool Registration & Workspace Context Slicing

To prevent context window bloat and reduce token costs by >85%, the platform implements **Workspace Context Slicing**:

* **Header-Based Context Slicing (`X-Workspace-Context`)**:
  - Requests containing headers like `X-Workspace-Context: physical-ai` receive only base tools + physical-AI domain tools, keeping prompt footprint **< 1,500 tokens** (down from 10,000+ tokens).
* **On-Demand Search Meta-Tool (`mcp__search_tools`)**:
  - Unlisted domain tools are lazy-loaded when the LLM queries the `mcp__search_tools(query, domain)` meta-tool.
* **Dynamic Tool Registration**:
  - Machine-to-machine agents register domain tools dynamically via `POST /api/v1/registry/register` using Keycloak M2M Bearer JWTs.

---

## 🌐 Federated MCP Server Integration

`MCPMultiplexerService` aggregates local tools alongside 3rd-party, Arm internal, and SaaS MCP servers into a single unified endpoint:

1. **Server Registration & Handshake (`POST /api/v1/registry/servers/register`)**:
   - Performs JSON-RPC 2.0 `tools/list` handshakes with upstream MCP servers (e.g., Official Arm Hardware Telemetry, KleidiAI GEMM benchmarks, or 3rd-party SaaS servers) and registers their schemas into `config/mcp_registry.json`.
2. **Transparent Tool Proxying (`POST /api/v1/registry/call`)**:
   - Automatically determines tool ownership. Local tools are executed via `SandboxOrchestrator`, while upstream tools are proxied transparently via JSON-RPC 2.0 `tools/call`.

---

## 🧪 Testing Architecture & Strategy

| Test Domain | Scope & Markers | Execution Strategy |
| :--- | :--- | :--- |
| **Unit & Integration** | Control plane routers, auth, & worker REPL (`-m "not kind and not heavy"`) | Fast PR Gate (`platform_ci_cd.yml`) |
| **E2E Gateway Smoke** | Lightweight KinD cluster validation (`tests/e2e/test_smoke.py`) | Fast PR Gate (`platform_ci_cd.yml`) |
| **Heavy E2E Benchmarks** | Multi-turn agent scenarios & performance (`-m "heavy"`) | Scheduled / Labeled (`e2e-benchmarks.yml`) |

### Execution Commands

```bash
# Sync local virtual environment
uv sync

# Run fast unit & integration tests (< 5s)
uv run pytest -m "not kind and not heavy"

# Run fast gateway smoke suite on KinD
E2E_TARGET=kind GATEWAY_BASE_URL=http://localhost:8080 uv run pytest tests/e2e/test_smoke.py -v

# Run heavy multi-turn agent benchmarks
uv run pytest tests/e2e/test_scenarios.py -v -m "heavy"
```

---

## 🔮 Future Roadmap & Multi-Tenancy

* **Multi-Cloud & On-Premises Arm Bare-Metal**:
  - Extend `SandboxOrchestrator` to schedule workloads across AWS Graviton3/4, Azure Cobalt 100, and on-premises Arm Neoverse V2 bare-metal clusters.

---

## 📄 License

Apache-2.0 License. See [LICENSE](LICENSE) for details.
