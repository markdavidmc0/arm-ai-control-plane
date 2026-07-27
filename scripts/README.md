# Platform Automation & Utility Scripts

This directory contains the core operational scripts and CLI tools for managing API key provisioning, M2M benchmarking, local developer testing, and automated cloud disaster recovery.

---

## 📋 Quick Reference Table

| Script | Purpose & Scope | Key Flags & Environment Variables | Usage Example |
| :--- | :--- | :--- | :--- |
| **`manage_keys.py`** | Provisions, lists, and revokes salted SHA-256 API keys (`arm_dev_*`, `arm_m2m_*`). | `create`, `list`, `revoke`, `--name`, `--role`, `--scopes` | `./scripts/manage_keys.py create --name "Dev Key" --role dev` |
| **`ci_mcp_client.py`** | M2M client script for GitHub Actions CI/CD PR benchmarking. | `--workload-path`, `--endpoint-url`, `ARM_M2M_API_KEY` | `./scripts/ci_mcp_client.py --workload-path workloads/04-physical-ai` |
| **`provision_and_test.sh`** | Developer CLI for local `--dry-run` testing and interactive cloud provisioning. | `--dry-run`, `--apply` | `./scripts/provision_and_test.sh --dry-run` |
| **`recreate_cluster_dr.sh`** | Non-interactive Disaster Recovery (DR) & 1-command cluster redeployment script. | `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_ZONE` | `GCP_PROJECT_ID=my-project ./scripts/recreate_cluster_dr.sh` |

---

## 🛠️ Detailed Script Documentation

### 1. `manage_keys.py` (API Key Provisioning)
Manages plain-text API keys (`arm_dev_*`, `arm_m2m_*`, `arm_judge_*`) and persists salted SHA-256 digests to `config/keys.json`.

```bash
# Create a new Developer key
./scripts/manage_keys.py create --name "Alice Dev Key" --role dev --scopes "compiler,autotuner"

# List all stored keys
./scripts/manage_keys.py list

# Revoke a key by ID
./scripts/manage_keys.py revoke --key-id key_dev_a1b2
```

---

### 2. `ci_mcp_client.py` (M2M CI/CD Benchmark Client)
Zero-dependency script used by GitHub Actions workflows in workload repositories to run M2M benchmarks against the Control Plane and generate Markdown reports for PR comments.

```bash
# Run against a local Gateway endpoint
./scripts/ci_mcp_client.py --workload-path workloads/04-physical-ai --endpoint-url http://127.0.0.1:10000 --mock
```

---

### 3. `provision_and_test.sh` (Local Dev & Testing CLI)
Interactive script for local development and smoke testing.
* **`--dry-run`**: Launches a transient FastAPI server on `localhost:8000`, executes 4 E2E smoke tests, and cleans up automatically.
* **`--apply`**: Provisions cloud resources using `provision_config.json`.

```bash
# Run local offline dry-run test
./scripts/provision_and_test.sh --dry-run
```

---

### 4. `recreate_cluster_dr.sh` (Disaster Recovery & Full Cluster Redeployment)
Non-interactive, 1-command script that provisions/redeploys the complete GKE cluster with Arm Tau T2A nodes, gVisor sandboxing, **Keycloak OIDC**, Envoy Edge Guard, Control Plane Gateway, and all in-house MCP servers in under 5 minutes.

```bash
export GCP_PROJECT_ID="my-arm-ai-project"
export GCP_REGION="us-central1"
export GCP_ZONE="us-central1-a"

./scripts/recreate_cluster_dr.sh
```
