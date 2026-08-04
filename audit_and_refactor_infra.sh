#!/usr/bin/env bash
set -euo pipefail

# Color formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

INFRA_DIR="infra"
DEPLOY_DIR="${INFRA_DIR}/deployments"
TF_DIR="${INFRA_DIR}/terraform"

APPLY_MODE=false
if [[ "${1:-}" == "--apply" ]]; then
  APPLY_MODE=true
fi

echo -e "${CYAN}================================================================${NC}"
echo -e "${CYAN} 🔍 Infrastructure Audit & Domain Separation Analysis ${NC}"
echo -e "${CYAN}================================================================${NC}\n"

# 1. Inspect Existing Deployment Manifests
echo -e "${YELLOW}[1/3] Scanning Kubernetes Manifests in ${DEPLOY_DIR}...${NC}"

declare -A MANIFEST_MAP=(
  ["gateway-and-envoy.yaml"]="control-plane"
  ["ingress.yaml"]="control-plane"
  ["internal-https-proxy.yaml"]="control-plane"
  ["keycloak.yaml"]="control-plane"
  ["in-house-mcp-servers.yaml"]="data-plane"
  ["runtime-class.yaml"]="data-plane"
  ["coredns-custom.yaml"]="shared"
  ["kind-config.yaml"]="shared"
)

FOUND_MANIFESTS=()
for file in "${!MANIFEST_MAP[@]}"; do
  target_domain="${MANIFEST_MAP[$file]}"
  if [ -f "${DEPLOY_DIR}/${file}" ]; then
    echo -e "  ${GREEN}✓ Found:${NC} ${file} -> Target: ${DEPLOY_DIR}/${target_domain}/"
    FOUND_MANIFESTS+=("${file}")
  fi
done

# 2. Inspect Existing Terraform Infrastructure
echo -e "\n${YELLOW}[2/3] Scanning Terraform Files in ${TF_DIR}...${NC}"
TF_FILES=("arc.tf" "iam.tf" "main.tf" "outputs.tf" "variables.tf" "provision_config.template.json")
for tf_file in "${TF_FILES[@]}"; do
  if [ -f "${TF_DIR}/${tf_file}" ]; then
    echo -e "  ${GREEN}✓ Found:${NC} ${TF_DIR}/${tf_file}"
  fi
done

# 3. Gap Analysis & Missing File Advice
echo -e "\n${YELLOW}[3/3] Infrastructure Gap Analysis & Missing Components${NC}"
echo -e "${CYAN}----------------------------------------------------------------${NC}"

MISSING_CRITICAL=0

# Check for Network Policies (Data Plane Boundary)
if [ ! -f "${DEPLOY_DIR}/data-plane/network-policy.yaml" ] && [ ! -f "${DEPLOY_DIR}/network-policy.yaml" ]; then
  echo -e "  ${RED}❌ MISSING CRITICAL:${NC} Data Plane NetworkPolicy (${DEPLOY_DIR}/data-plane/network-policy.yaml)"
  echo -e "     -> Risk: Without this, gVisor worker pods can accept direct ingress from non-control-plane resources."
  MISSING_CRITICAL=$((MISSING_CRITICAL + 1))
fi

# Check for Data Plane Resource Quotas
if [ ! -f "${DEPLOY_DIR}/data-plane/resource-quota.yaml" ] && [ ! -f "${DEPLOY_DIR}/resource-quota.yaml" ]; then
  echo -e "  ${YELLOW}⚠️  MISSING RECOMMENDED:${NC} Resource Quotas (${DEPLOY_DIR}/data-plane/resource-quota.yaml)"
  echo -e "     -> Risk: Sandboxed execution workloads could consume excessive CPU/Memory on host nodes."
  MISSING_CRITICAL=$((MISSING_CRITICAL + 1))
fi

# Check for Terraform Modularization Structure
if [ ! -d "${TF_DIR}/modules/data_plane" ]; then
  echo -e "  ${RED}❌ MISSING STRUCTURE:${NC} Dedicated Terraform modules (${TF_DIR}/modules/{control_plane,data_plane,platform})"
  echo -e "     -> Risk: Un-isolated IAM policies and node pool definitions in single flat terraform files."
  MISSING_CRITICAL=$((MISSING_CRITICAL + 1))
fi

echo -e "${CYAN}----------------------------------------------------------------${NC}\n"

if [ "$APPLY_MODE" = false ]; then
  echo -e "${YELLOW}DRY RUN COMPLETE.${NC} To perform file moves and modularize Terraform structure, run:"
  echo -e "  ${GREEN}./audit_and_refactor_infra.sh --apply${NC}\n"
  exit 0
fi

# ==============================================================================
# EXECUTION PHASE (Runs only when --apply is passed)
# ==============================================================================
echo -e "${CYAN}🚀 Applying domain separation refactors...${NC}"

# Create Target Directories
mkdir -p "${DEPLOY_DIR}/control-plane"
mkdir -p "${DEPLOY_DIR}/data-plane"
mkdir -p "${DEPLOY_DIR}/shared"
mkdir -p "${TF_DIR}/modules/control_plane"
mkdir -p "${TF_DIR}/modules/data_plane"
mkdir -p "${TF_DIR}/modules/platform"

# Move Deployment Files
for file in "${!MANIFEST_MAP[@]}"; do
  target_domain="${MANIFEST_MAP[$file]}"
  if [ -f "${DEPLOY_DIR}/${file}" ]; then
    mv "${DEPLOY_DIR}/${file}" "${DEPLOY_DIR}/${target_domain}/"
    echo "Moved ${file} -> ${DEPLOY_DIR}/${target_domain}/"
  fi
done

# Modularize Base Terraform
if [ -f "${TF_DIR}/arc.tf" ]; then
  mv "${TF_DIR}/arc.tf" "${TF_DIR}/modules/platform/arc.tf"
  echo "Moved arc.tf -> ${TF_DIR}/modules/platform/"
fi

echo -e "${GREEN}✅ Domain migration complete! Review missing files described above.${NC}"
