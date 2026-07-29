#!/usr/bin/env bash
set -euo pipefail

# Determine script directory and repo root dynamically
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

# Determine config file path
if [[ -f "config/provision_config.json" ]]; then
  CONFIG_FILE="config/provision_config.json"
elif [[ -f "provision_config.json" ]]; then
  CONFIG_FILE="provision_config.json"
else
  echo "❌ Error: config/provision_config.json not found!"
  exit 1
fi

# Dynamically parse variables to prevent hardcoded drift
PROJECT_ID=$(python3 -c "import json; print(json.load(open('${CONFIG_FILE}'))['project_id'])")
ZONE=$(python3 -c "import json; print(json.load(open('${CONFIG_FILE}'))['zone'])")
CLUSTER_NAME=$(python3 -c "import json; print(json.load(open('${CONFIG_FILE}'))['cluster_name'])")
NODE_POOL="arm-sandbox-node-pool"

echo "========================================================="
echo "❄️  Scaling GKE Node Pool to ZERO (Dormant Mode)"
echo "Cluster:    ${CLUSTER_NAME}"
echo "Node Pool:  ${NODE_POOL}"
echo "Project ID: ${PROJECT_ID}"
echo "Zone:       ${ZONE}"
echo "========================================================="

# Execute GKE resize command
gcloud container clusters resize "${CLUSTER_NAME}" \
  --node-pool "${NODE_POOL}" \
  --num-nodes 0 \
  --zone "${ZONE}" \
  --project "${PROJECT_ID}" \
  --quiet

echo "========================================================="
echo "✅ Node pool successfully scaled down to 0 nodes!"
echo "Your cluster is now running at 0 active nodes (Zero-Cost Dormancy)."
echo "========================================================="
