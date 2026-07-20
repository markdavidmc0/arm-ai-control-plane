#!/usr/bin/env bash
set -euo pipefail

# Determine script directory and repo root dynamically
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

# Verify configuration file presence
if [[ ! -f "provision_config.json" ]]; then
  echo "❌ Error: provision_config.json not found in repository root!"
  exit 1
fi

# Dynamically parse variables to prevent hardcoded drift
PROJECT_ID=$(python3 -c "import json; print(json.load(open('provision_config.json'))['project_id'])")
ZONE=$(python3 -c "import json; print(json.load(open('provision_config.json'))['zone'])")
CLUSTER_NAME=$(python3 -c "import json; print(json.load(open('provision_config.json'))['cluster_name'])")
NODE_POOL="arm-sandbox-node-pool"
TARGET_NODES=2

echo "========================================================="
echo "☀️  Scaling GKE Node Pool UP (Active Mode)"
echo "Cluster:      ${CLUSTER_NAME}"
echo "Node Pool:    ${NODE_POOL}"
echo "Project ID:   ${PROJECT_ID}"
echo "Zone:         ${ZONE}"
echo "Target Nodes: ${TARGET_NODES}"
echo "========================================================="

# Execute GKE resize command
gcloud container clusters resize "${CLUSTER_NAME}" \
  --node-pool "${NODE_POOL}" \
  --num-nodes "${TARGET_NODES}" \
  --zone "${ZONE}" \
  --project "${PROJECT_ID}" \
  --quiet

echo "========================================================="
echo "✅ Node pool successfully scaled up to ${TARGET_NODES} nodes!"
echo "Your cluster is now ready and actively running Arm workloads."
echo "========================================================="
