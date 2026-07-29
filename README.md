# 🛡️ Arm Federated AI Control Plane (MVCP)

[![Platform Control Plane CI/CD Pipeline](https://github.com/markdavidmc0/arm-ai-control-plane/actions/workflows/platform_ci_cd.yml/badge.svg)](https://github.com/markdavidmc0/arm-ai-control-plane/actions/workflows/platform_ci_cd.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Arm Tau T2A](https://img.shields.io/badge/architecture-Arm64-orange.svg)](https://cloud.google.com/compute/docs/general-purpose-machines#t2a_machines)
[![gVisor Sandbox](https://img.shields.io/badge/sandbox-gVisor-green.svg)](https://gvisor.dev/)

An enterprise-grade, zero-trust **Master Model Context Protocol (MVCP) Control Plane** optimized for **Arm Neoverse / Tau T2A architecture** running on Google Kubernetes Engine (GKE) with gVisor sandbox isolation.

---

## 🏛️ System Architecture

```
                                 ┌──────────────────────────────────────────────┐
                                 │              Private VPC Network             │
                                 │            (mvcp-vpc-network)                │
                                 │                                              │
 ┌──────────────────────┐  OIDC  │  ┌─────────────────┐    ┌─────────────────┐  │
 │ GitHub Actions CI/CD │ ───────┼─>│ Keycloak (OIDC) │    │  MVCP Gateway   │  │
 │ (mvcp-github-ci-sa)  │        │  │ keycloak.arm.   │    │ gateway.arm.    │  │
 └──────────────────────┘        │  │    internal     │    │    internal     │  │
                                 │  └────────┬────────┘    └────────┬────────┘  │
                                 │           │                      │           │
                                 │           ▼                      ▼           │
                                 │  ┌────────────────────────────────────────┐  │
                                 │  │        GKE Internal Ingress (L7)       │  │
                                 │  │         (arm-platform-ingress)         │  │
                                 │  └──────────────────┬─────────────────────┘  │
                                 │                     │                        │
                                 │                     ▼                        │
                                 │  ┌────────────────────────────────────────┐  │
                                 │  │      Envoy Edge Guard (Port 10000)     │  │
                                 │  └──────────────────┬─────────────────────┘  │
                                 │                     │                        │
                                 │                     ▼                        │
                                 │  ┌────────────────────────────────────────┐  │
                                 │  │      Arm Sandbox Worker Node Pool      │  │
                                 │  │   (Arm Tau T2A + gVisor Isolation)     │  │
                                 │  └────────────────────────────────────────┘  │
                                 └──────────────────────────────────────────────┘
```

---

## ✨ Key Features

* **🛡️ Arm Tau T2A + gVisor Sandboxing**: Secure, high-throughput container runtime on 64-bit Armv8.2-A processors using gVisor container isolation.
* **🔑 OAuth2 / OIDC M2M Authentication**: Keycloak machine-to-machine authentication with Google Secret Manager client credential management.
* **🌐 Private VPC & Cloud DNS**: Zero public internet exposure. Service discovery via private Cloud DNS (`keycloak.arm.internal` and `gateway.arm.internal`).
* **🚦 Unified GKE Internal Ingress**: Port-free L7 HTTP routing and Container-Native Load Balancing (NEGs).
* **🤖 Master Model Context Protocol (MCP)**: Automated discovery, dynamic routing, and health monitoring for federated MCP servers.
* **⚙️ 100% Infrastructure-as-Code**: Fully automated GCP provisioning using Terraform and GitHub Actions OIDC Workload Identity Federation.

---

## 🚀 Quick Start

### 1. Local Development & Testing

Install dependencies using `uv` and run the test suite:

```bash
# Sync local virtual environment
uv sync

# Run pytest test suite
uv run pytest
```

### 2. Infrastructure Provisioning (Terraform)

Provision the complete GCP infrastructure (VPC, GKE Arm Node Pool, Secret Manager, IAM, Cloud DNS):

```bash
cd terraform
terraform init
terraform apply \
  -var="project_id=sovereign-ai-495715" \
  -var="region=us-central1" \
  -var="zone=us-central1-a"
```

---

## 🔒 Security & Least Privilege

* **Workload Identity**: In-cluster Kubernetes Service Accounts are bound 1-to-1 with GCP Service Accounts without static JSON credentials.
* **GCP Secret Manager**: Sensitive M2M credentials are generated dynamically and stored encrypted in Google Secret Manager.
* **Zero Public Exposure**: Internal Ingress and Tailscale integration ensure zero exposed external IP addresses.

---

## 📄 License

Apache-2.0 License. See [LICENSE](LICENSE) for details.
