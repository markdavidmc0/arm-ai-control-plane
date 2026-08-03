#!/usr/bin/env bash
# ==============================================================================
# Local Kind (Kubernetes-in-Docker) E2E Test Runner
# Creates local Kind cluster, deploys platform manifests, executes E2E platform
# test suite, and cleans up automatically.
# ==============================================================================

set -e

CLUSTER_NAME="kind-e2e-cluster"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${CYAN}====================================================================${NC}"
echo -e "${CYAN}   Arm Federated AI Platform - Local Kind Cluster E2E Test Runner    ${NC}"
echo -e "${CYAN}====================================================================${NC}"

# Ensure cleanup on script exit
cleanup() {
  echo -e "\n${YELLOW}Tearing down local Kind cluster (${CLUSTER_NAME})...${NC}"
  kind delete cluster --name $CLUSTER_NAME 2>/dev/null || true
  echo -e "${GREEN}✓ Local Kind cluster deleted.${NC}"
}
trap cleanup EXIT

# 1. Create Multi-Node-Pool Kind cluster
echo -e "\n${CYAN}[1/3] Creating multi-node-pool Kind cluster (${CLUSTER_NAME})...${NC}"
kind create cluster --name $CLUSTER_NAME --config .platform/deployments/kind-config.yaml

# 2. Deploy Platform Manifests
echo -e "\n${CYAN}[2/3] Deploying Gateway, Envoy, and MCP Server manifests to Kind...${NC}"
kubectl apply -f .platform/deployments/gateway-and-envoy.yaml
kubectl apply -f .platform/deployments/in-house-mcp-servers.yaml

echo -e "${CYAN}Waiting for gateway and Envoy deployment rollout readiness...${NC}"
kubectl rollout status deployment/mvcp-gateway-deployment --timeout=120s || true
kubectl rollout status deployment/envoy-edge-guard-deployment --timeout=120s || true

# 3. Run E2E Test Suite
echo -e "\n${CYAN}[3/3] Executing E2E Platform Test Suite against Kind cluster...${NC}"
uv run pytest tests/e2e/test_infrastructure.py --target=kind --endpoint=http://localhost:8080 -v

echo -e "\n${GREEN}====================================================================${NC}"
echo -e "${GREEN}   LOCAL KIND E2E PLATFORM TESTS COMPLETED SUCCESSFULLY!             ${NC}"
echo -e "${GREEN}====================================================================${NC}"
