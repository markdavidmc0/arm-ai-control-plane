#!/usr/bin/env bash
# ==============================================================================
# Disaster Recovery (DR) & Environment Replication Script
# ==============================================================================
# Recreates or replicates the entire Arm MVCP Platform stack from scratch in
# under 5 minutes: VPC Networking, GKE Arm Tau T2A Node Pools, gVisor Sandboxes,
# Keycloak OIDC, Envoy Edge Guard, Control Plane Gateway, and In-House MCP Servers.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PROJECT_ID="${GCP_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || echo "")}"
REGION="${GCP_REGION:-us-central1}"
ZONE="${GCP_ZONE:-us-central1-a}"
CLUSTER_NAME="${GKE_CLUSTER_NAME:-mvcp-gke-cluster}"

echo "=========================================================================="
echo "🚨 STARTING DISASTER RECOVERY / ENVIRONMENT REPLICATION PROCEDURE"
echo "=========================================================================="
echo "  Target Project : ${PROJECT_ID}"
echo "  Target Region  : ${REGION}"
echo "  Target Zone    : ${ZONE}"
echo "  Cluster Name   : ${CLUSTER_NAME}"
echo "=========================================================================="

if [ -z "${PROJECT_ID}" ]; then
  echo "❌ ERROR: GCP_PROJECT_ID is not set. Please export GCP_PROJECT_ID or set active gcloud project." >&2
  exit 1
fi

# Step 1: Provision Infrastructure via Terraform
echo -e "\n📦 Step 1: Executing Terraform Infrastructure Provisioning..."
cd "${REPO_ROOT}/terraform"

terraform init -input=false
terraform apply -auto-approve \
  -var="project_id=${PROJECT_ID}" \
  -var="region=${REGION}" \
  -var="zone=${ZONE}" \
  -var="cluster_name=${CLUSTER_NAME}"

# Step 2: Fetch Cluster Credentials
echo -e "\n🔑 Step 2: Authenticating kubectl to GKE Cluster..."
gcloud container clusters get-credentials "${CLUSTER_NAME}" \
  --zone "${ZONE}" \
  --project "${PROJECT_ID}"

# Step 3: Apply Kubernetes Deployment Manifests
echo -e "\n☸️ Step 3: Deploying Keycloak, Gateway, Envoy, and In-House MCP Servers..."
cd "${REPO_ROOT}"

kubectl apply -f .platform/deployments/keycloak.yaml
kubectl apply -f .platform/deployments/gateway-and-envoy.yaml
kubectl apply -f .platform/deployments/in-house-mcp-servers.yaml

# Step 4: Verify Deployment Rollout Status
echo -e "\n⏳ Step 4: Verifying Deployment Rollout Health..."
kubectl rollout status deployment/keycloak-deployment --timeout=180s
kubectl rollout status deployment/mvcp-gateway-deployment --timeout=180s
kubectl rollout status deployment/envoy-edge-guard-deployment --timeout=180s
kubectl rollout status deployment/official-arm-mcp-deployment --timeout=180s
kubectl rollout status deployment/performix-mcp-deployment --timeout=180s
kubectl rollout status deployment/arm-metis-mcp-deployment --timeout=180s

echo -e "\n=========================================================================="
echo "✅ DISASTER RECOVERY / ENVIRONMENT REPLICATION COMPLETED SUCCESSFULLY!"
echo "=========================================================================="
echo "  Keycloak OIDC Service         : http://keycloak-service:8080"
echo "  Control Plane Gateway Service : http://mvcp-gateway-service:8000"
echo "  Envoy Edge Guard Ingress      : http://envoy-edge-guard-service:10000"
echo "  Official Arm MCP Server       : http://official-arm-mcp-service:8000"
echo "  Performix Autotuner           : http://performix-mcp-service:8080"
echo "  Arm Metis Simulator           : http://arm-metis-mcp-service:9000"
echo "=========================================================================="
