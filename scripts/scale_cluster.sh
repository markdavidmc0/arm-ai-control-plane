#!/usr/bin/env bash
# Unified GKE Cluster Node Pool Scaling Script

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

# Parse action or flag (up, down, status, or explicit integer)
ACTION="${1:-"status"}"

case "${ACTION}" in
  up|--up|-u)
    TARGET_NODES=2
    MODE_EMOJI="☀️"
    MODE_LABEL="Scaling GKE Node Pool UP (Active Mode)"
    ;;
  down|--down|-d)
    TARGET_NODES=0
    MODE_EMOJI="❄️"
    MODE_LABEL="Scaling GKE Node Pool to ZERO (Dormant Mode)"
    ;;
  status|--status|-s)
    echo "========================================================="
    echo "🔍 Checking Current GKE Node Pool Status"
    echo "Cluster:    ${CLUSTER_NAME}"
    echo "Node Pool:  ${NODE_POOL}"
    echo "Project ID: ${PROJECT_ID}"
    echo "Zone:       ${ZONE}"
    echo "========================================================="
    gcloud container node-pools describe "${NODE_POOL}" \
      --cluster "${CLUSTER_NAME}" \
      --zone "${ZONE}" \
      --project "${PROJECT_ID}" \
      --format="value(initialNodeCount, status)"
    exit 0
    ;;
  *)
    if [[ "${ACTION}" =~ ^[0-9]+$ ]]; then
      TARGET_NODES="${ACTION}"
      MODE_EMOJI="⚙️"
      MODE_LABEL="Scaling GKE Node Pool to ${TARGET_NODES} nodes"
    else
      echo "Usage: $0 {up|down|status|<num_nodes>}"
      echo "Flags: $0 [--up | --down | --status]"
      exit 1
    fi
    ;;
esac

echo "========================================================="
echo "${MODE_EMOJI}  ${MODE_LABEL}"
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
echo "✅ Node pool successfully scaled to ${TARGET_NODES} nodes!"
echo "========================================================="
